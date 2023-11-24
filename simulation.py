import simpy
import random
import yaml
import matplotlib.pyplot as plt


class Facility:
    def __init__(
        self,
        env,
        name,
        capacity,
        destination=None,
        initial_inventory=0,
        transit_times=None,
    ):
        self.env = env
        self.name = name
        self.destination = destination
        self.transit_times = transit_times or {}
        self.inventory = simpy.Container(env, init=initial_inventory, capacity=capacity)
        self.inventory_log = []
        self.log_inventory(0)  # Log initial state
        self.on_order = 0

    def log_inventory(self, time):
        """Logs the current inventory level along with the simulation time."""
        self.inventory_log.append((time, self.inventory.level))

    def receive_drug(self, quantity):
        """Receives a shipment of drugs and adds it to the inventory."""
        yield self.inventory.put(quantity)
        print(
            f"Received {quantity} units of drug at {self.name} on day {self.env.now}."
        )
        self.log_inventory(self.env.now)
        self.on_order -= quantity

    def dispatch_drug(self, quantity):
        """Dispatches drugs from the facility to its destination."""
        if self.inventory.level >= quantity:
            yield self.inventory.get(quantity)
            print(
                f"Dispatched {quantity} units of drug from {self.name} on day {self.env.now}."
            )
            self.log_inventory(self.env.now)
            if self.destination:
                yield self.env.process(
                    transport_drug(
                        self.env, self, self.destination, quantity, self.transit_times
                    )
                )
        else:
            print(
                f"Not enough inventory to dispatch {quantity} units on day {self.env.now} at {self.name}."
            )


class ManufacturingFacility(Facility):
    def __init__(self, env, destination, production_rate, capacity, transit_times):
        super().__init__(env, "manufacturer", capacity, destination, 0, transit_times)
        self.production_rate = production_rate  # units per day

    def produce_drug(self, quantity):
        """Simulates the production of the drug."""
        while True:
            # Wait for a day
            production_time = quantity / self.production_rate
            yield self.env.timeout(
                production_time
            )  # Simulates the passage of production time
            yield self.inventory.put(
                quantity
            )  # Add the produced drugs to the facility's inventory
            self.log_inventory(self.env.now)
            print(f"Produced {quantity} units of the drug.")


class StorageFacility(Facility):
    def __init__(
        self, env, name, destination, initial_inventory, capacity, transit_times
    ):
        super().__init__(
            env, name, capacity, destination, initial_inventory, transit_times
        )


class TrialSite(Facility):
    def __init__(self, env, initial_inventory, dosage_schedule, capacity):
        super().__init__(env, "trial_site", capacity, None, initial_inventory, None)
        self.patients = 0
        self.dosage_schedule = dosage_schedule  # Dosage per patient
        self.patient_log = []

    def enroll_patient(self, dosage):
        """Handle the logistics of enrolling a new patient."""
        self.patients += 1
        self.patient_log.append((self.env.now, self.patients))
        dosage_schedule = DosageSchedule(
            dose_amount=dosage["amount"], dose_interval=dosage["interval"]
        )
        self.env.process(
            self.patient_demand(dosage_schedule)
        )  # Start the demand process for the new patient

    def patient_demand(self, dosage_schedule):
        """Simulates the drug demand for an individual patient."""
        while True:
            # Wait until the next dosage is due
            yield self.env.timeout(dosage_schedule.get_next_dose_time())

            # Consume drug, generate demand and heck if enough drug is available for consumption
            amount = dosage_schedule.next_dose()
            if self.inventory.level >= amount:
                # Consume the drug from inventory
                yield self.inventory.get(amount)
                # print(f"Consumed {amount} units of drug on day {self.env.now}.")
            else:
                # Not enough drug available; raise a stockout error
                raise ValueError(
                    f"Stockout occurred on day {self.env.now}: unable to consume {amount} units of drug."
                )

            # Log the current inventory level after consumption
            self.log_inventory(self.env.now)
            # print(f"Drug consumed by patient on day {self.env.now}")


class DosageSchedule:
    def __init__(self, dose_amount, dose_interval):
        """Initializes the dosage schedule for a patient."""
        self.dose_amount = dose_amount
        self.dose_interval = dose_interval
        self.next_dose_time = 1  # Tracks the time until the next dose for a patient

    def next_dose(self):
        """Schedules the next dose for a patient."""
        self.next_dose_time += self.dose_interval
        return self.dose_amount

    def get_next_dose_time(self):
        """Retrieves the time until the next dose is due."""
        return self.next_dose_time


class InventoryController:
    def __init__(
        self,
        env,
        facility,
        supplier,
        reorder_point,
        reorder_quantity,
        lead_time,
        forecast_window,
    ):
        self.env = env
        self.facility = facility
        self.supplier = supplier
        self.reorder_point = reorder_point
        self.reorder_quantity = reorder_quantity
        self.lead_time = lead_time
        self.forecast_window = (
            forecast_window  # Looking ahead 'forecast_window' days to anticipate demand
        )
        self.env.process(self.run())

    def run(self):
        while True:
            forecasted_demand = self.forecast_demand()
            projected_inventory = (
                self.facility.inventory.level
                + self.facility.on_order
                - forecasted_demand
            )
            if projected_inventory < self.reorder_point:
                yield self.env.process(self.place_order())
            yield self.env.timeout(1)  # Check inventory periodically

    def place_order(self):
        # Include logic to handle if the supplier cannot fulfill the entire order quantity
        print(
            f"Placing order for {self.reorder_quantity} units from {self.supplier.name}"
        )
        yield self.env.timeout(self.lead_time)  # Wait for the lead time
        yield self.env.process(self.supplier.dispatch_drug(self.reorder_quantity))
        self.facility.on_order += self.reorder_quantity

    def forecast_demand(self):
        # Simple demand forecast: average usage multiplied by forecast window
        average_daily_usage = self.calculate_average_daily_usage()
        return average_daily_usage * self.forecast_window

    def calculate_average_daily_usage(self):
        # Example logic for average daily usage
        # This could be based on historical usage data or other forecasting models
        # For now, we simply divide total usage by the number of days
        total_usage = sum(
            amount for _, amount in self.facility.inventory_log
        )  # Sum all the usage
        days_passed = self.env.now
        return total_usage / days_passed if days_passed > 0 else 0


def transport_drug(env, source, destination, quantity, transit_times):
    """Simulates the transportation of drugs."""
    default_time = transit_times["default"]
    transport_time = transit_times.get(
        f"{source.name}_to_{destination.name}", default_time
    )
    yield env.timeout(transport_time)  # Represents transport delay
    yield env.process(destination.receive_drug(quantity))  # Add drugs to destination
    print(
        f"Transported {quantity} units of the drug from {source.name} to {destination.name} on day {env.now}."
    )


def patient_enrollment(
    env, trial_site, mean_interarrival_time, dropout_rate, dosage, target_enrollment
):
    """Simulates patient enrollment over time."""
    while trial_site.patients <= target_enrollment:
        # Simulate the time until the next patient enrollment
        interarrival_time = random.expovariate(1.0 / mean_interarrival_time)

        # Wait for the next enrollment event
        yield env.timeout(interarrival_time)

        # Enroll the patient
        if random.random() >= dropout_rate:
            trial_site.enroll_patient(
                dosage
            )  # Add logic to handle patient enrollment and IMP demand
            # print(f"Patient enrolled on day {env.now}")
        # else:
        # print(f"Patient drop out on day {env.now}")


def plot_inventory_levels(inventory_log, title):
    times, levels = zip(*inventory_log)  # Unzip the log into times and levels
    plt.plot(times, levels, marker="o")
    plt.title(title)
    plt.xlabel("Simulation Time (days)")
    plt.ylabel("Inventory Level (units)")
    plt.grid(True)
    plt.show()


def plot_combined_inventory_levels(inventory_logs, labels, title):
    plt.figure(figsize=(10, 5))  # Set the figure size as needed
    for inventory_log, label in zip(inventory_logs, labels):
        times, levels = zip(*inventory_log)  # Unzip the log into times and levels
        plt.plot(times, levels, marker="o", label=label)

    plt.title(title)
    plt.xlabel("Simulation Time (days)")
    plt.ylabel("Inventory Level (units)")
    plt.legend()  # Display a legend to identify each line
    plt.grid(True)
    plt.show()


def run_simulation():
    env = simpy.Environment()

    with open("data.yml", "r") as file:
        config = yaml.safe_load(file)["trial_a"]

    dosage_schedule = DosageSchedule(
        dose_amount=config["dosage"]["amount"],
        dose_interval=config["dosage"]["interval"],
    )
    trial_site = TrialSite(
        env,
        initial_inventory=config["site"]["initial_inventory"],
        dosage_schedule=dosage_schedule,
        capacity=config["site"]["capacity"],
    )
    regional_storage = Facility(
        env,
        "regional_storage",
        destination=trial_site,
        initial_inventory=config["regional_storage"]["initial_inventory"],
        capacity=config["regional_storage"]["capacity"],
        transit_times=config["transit_times"],
    )
    central_storage = Facility(
        env,
        "central_storage",
        destination=regional_storage,
        initial_inventory=config["central_storage"]["initial_inventory"],
        capacity=config["central_storage"]["capacity"],
        transit_times=config["transit_times"],
    )
    manufacturer = ManufacturingFacility(
        env,
        destination=central_storage,
        production_rate=config["manufacturer"]["prod_rate"],
        capacity=config["manufacturer"]["capacity"],
        transit_times=config["transit_times"],
    )

    InventoryController(
        env=env,
        facility=central_storage,
        supplier=manufacturer,
        reorder_point=config["central_storage"]["reorder_point"],
        reorder_quantity=config["central_storage"]["reorder_quantity"],
        lead_time=config["transit_times"]["manufacturer_to_central_storage"],
        forecast_window=3,
    )
    InventoryController(
        env=env,
        facility=regional_storage,
        supplier=central_storage,
        reorder_point=config["regional_storage"]["reorder_point"],
        reorder_quantity=config["regional_storage"]["reorder_quantity"],
        lead_time=config["transit_times"]["central_storage_to_regional_storage"],
        forecast_window=3,
    )
    InventoryController(
        env=env,
        facility=trial_site,
        supplier=regional_storage,
        reorder_point=config["site"]["reorder_point"],
        reorder_quantity=config["site"]["reorder_quantity"],
        lead_time=config["transit_times"]["regional_storage_to_trial_site"],
        forecast_window=3,
    )

    # Start the enrollment process
    env.process(
        patient_enrollment(
            env,
            trial_site,
            config["mean_interarrival_time"],
            config["dropout_rate"],
            config["dosage"],
            config["target_enrollment"],
        )
    )
    # Start production and transportation processes
    env.process(manufacturer.produce_drug(config["manufacturer"]["produce"]))

    try:
        env.run(until=config["simulation_time"])  # for example, simulating for one year
    except ValueError:
        print("Failed with stockout!")

    manufacturer_inventory_levels = manufacturer.inventory_log
    central_storage_inventory_levels = central_storage.inventory_log
    regional_storage_inventory_levels = regional_storage.inventory_log
    site_inventory_levels = trial_site.inventory_log
    patient_levels = trial_site.patient_log

    if config["graph_strategy"] == "separate":
        # Call the plotting function for each facility
        plot_inventory_levels(
            manufacturer_inventory_levels, "Manufacturer Inventory Levels"
        )
        plot_inventory_levels(
            central_storage_inventory_levels, "Central Storage Inventory Levels"
        )
        plot_inventory_levels(
            regional_storage_inventory_levels, "Regional Storage Inventory Levels"
        )
        plot_inventory_levels(site_inventory_levels, "Trial Site Inventory Levels")
    elif config["graph_strategy"] == "combined":
        # Call the combined plotting function with all facility logs
        inventory_logs = [
            manufacturer_inventory_levels,
            central_storage_inventory_levels,
            regional_storage_inventory_levels,
            site_inventory_levels,
            patient_levels,
        ]

        labels = [
            "Manufacturer Inventory",
            "Central Storage Inventory",
            "Regional Storage Inventory",
            "Trial Site Inventory",
            "Patient Count",
        ]

        plot_combined_inventory_levels(
            inventory_logs, labels, "Combined Inventory Levels Over Time"
        )


run_simulation()
