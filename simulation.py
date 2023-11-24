import simpy
import random
import yaml
import matplotlib.pyplot as plt


class ManufacturingFacility:
    def __init__(self, env, production_rate, capacity):
        self.env = env
        self.production_rate = production_rate  # units per day
        self.capacity = simpy.Container(
            env, init=0, capacity=capacity
        )  # represents the on-hand inventory of drugs
        self.inventory_log = []
        self.log_inventory(0)  # Log initial state

    def produce_drug(self, quantity):
        """Simulates the production of the drug."""
        production_time = quantity / self.production_rate
        yield self.env.timeout(
            production_time
        )  # Simulates the passage of production time
        yield self.capacity.put(
            quantity
        )  # Add the produced drugs to the facility's inventory
        self.log_inventory(self.env.now)
        print(f"Produced {quantity} units of the drug.")

    def log_inventory(self, time):
        """Logs the current inventory level along with the simulation time."""
        self.inventory_log.append((time, self.capacity.level))


class StorageFacility:
    def __init__(self, env, name, initial_inventory, capacity):
        self.env = env
        self.name = name
        self.inventory = simpy.Container(
            env, init=initial_inventory, capacity=capacity
        )  # Drug inventory
        self.inventory_log = []
        self.log_inventory(0)  # Log initial state

    def order_drug(self, quantity):
        """Processes an order and waits if necessary for stock to be available."""
        yield self.inventory.get(quantity)
        print(f"Order fulfilled for {quantity} units of the drug.")

    def receive_drug(self, quantity):
        """Receives a shipment of drugs and adds it to the inventory."""
        yield self.inventory.put(quantity)
        print(f"Received an order of {quantity} units of the drug. {self.env.now}")
        self.log_inventory(self.env.now)

    def dispatch_drug(self, quantity):
        """Dispatch drugs for transportation."""
        yield self.inventory.get(quantity)
        print(f"Dispatched {quantity} units for drug on day {self.env.now}.")
        self.log_inventory(self.env.now)

    def log_inventory(self, time):
        """Logs the current inventory level along with the simulation time."""
        self.inventory_log.append((time, self.inventory.level))


# Subclass for RegionalStorageFacility
class RegionalStorageFacility(StorageFacility):
    def __init__(self, env, name, initial_inventory, capacity):
        super().__init__(env, name, initial_inventory, capacity)


# Subclass for CentralStorageFacility
class CentralStorageFacility(StorageFacility):
    def __init__(self, env, name, initial_inventory, capacity):
        super().__init__(env, name, initial_inventory, capacity)


class TrialSite:
    def __init__(self, env, initial_inventory, dosage_schedule, capacity):
        self.env = env
        self.patients = 0
        self.dosage_schedule = dosage_schedule  # Dosage per patient
        self.inventory = simpy.Container(env, init=initial_inventory, capacity=capacity)
        self.inventory_log = []
        self.log_inventory(0)  # Log initial state

    def request_resupply(self, storage_facility, quantity):
        """Requests a resupply of drugs from a storage facility."""
        self.env.process(storage_facility.order_drug(quantity))
        print(f"Requested resupply of {quantity} units of the drug.")

    def receive_drug(self, quantity):
        """Receives a shipment of drugs."""
        yield self.inventory.put(quantity)
        print(f"Trial site received {quantity} units of the drug.")
        self.log_inventory(self.env.now)

    def enroll_patient(self, dosage):
        """Handle the logistics of enrolling a new patient."""
        self.patients += 1
        dosage_schedule = DosageSchedule(
            dose_amount=dosage["amount"], dose_interval=dosage["interval"]
        )
        self.env.process(
            self.patient_demand(dosage_schedule)
        )  # Start the demand process for the new patient

    def consume_drug(self, amount):
        """Logic to consume drug and potentially trigger resupply."""
        # Check if enough drug is available for consumption
        if self.inventory.level >= amount:
            # Consume the drug from inventory
            yield self.inventory.get(amount)
            print(f"Consumed {amount} units of drug on day {self.env.now}.")
        else:
            print(
                f"Not enough drug available to consume {amount} units on day {self.env.now}."
            )
            # You may want to add logic here to handle the case when there's not enough drug

        # Log the current inventory level after consumption
        self.log_inventory(self.env.now)

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
                print(f"Consumed {amount} units of drug on day {self.env.now}.")
            else:
                print(
                    f"Not enough drug available to consume {amount} units on day {self.env.now}."
                )
                # You may want to add logic here to handle the case when there's not enough drug

            # Log the current inventory level after consumption
            self.log_inventory(self.env.now)
            print(f"Drug consumed by patient on day {self.env.now}")

    def receive_drug(self, quantity):
        """Receives a shipment of drugs."""
        yield self.inventory.put(quantity)
        print(f"Received {quantity} units of drug on day {self.env.now}.")
        self.log_inventory(self.env.now)

    def log_inventory(self, time):
        """Logs the current inventory level along with the simulation time."""
        self.inventory_log.append((time, self.inventory.level))


class DosageSchedule:
    def __init__(self, dose_amount, dose_interval):
        """
        Initializes the dosage schedule for a patient.

        :param dose_amount: The amount of drug administered in each dose.
        :param dose_interval: The time interval between doses in days.
        """
        self.dose_amount = dose_amount
        self.dose_interval = dose_interval
        self.next_dose_time = 1  # Tracks the time until the next dose for a patient

    def next_dose(self):
        """
        Schedules the next dose for a patient.

        :return: The amount of drug for the next dose.
        """
        self.next_dose_time += self.dose_interval
        return self.dose_amount

    def get_next_dose_time(self):
        """
        Retrieves the time until the next dose is due.

        :return: The time until the next dose in days.
        """
        return self.next_dose_time


def transport_drug(env, source, destination, quantity, transit_times):
    """Simulates the transportation of drugs."""
    default_time = transit_times["default"]
    transport_time = transit_times.get(source + "_to_" + destination, default_time)
    yield env.timeout(transport_time)  # Represents transport delay
    source.dispatch_drug(quantity)  # Get drugs from source
    yield env.process(destination.receive_drug(quantity))  # Add drugs to destination
    print(
        f"Transported {quantity} units of the drug from {source.name} to {destination.name} on day {env.now}."
    )


def patient_enrollment(env, trial_site, mean_interarrival_time, dropout_rate, dosage):
    """Simulates patient enrollment over time."""
    while True:
        # Simulate the time until the next patient enrollment
        interarrival_time = random.expovariate(1.0 / mean_interarrival_time)

        # Wait for the next enrollment event
        yield env.timeout(interarrival_time)

        # Enroll the patient
        if random.random() >= dropout_rate:
            trial_site.enroll_patient(
                dosage
            )  # Add logic to handle patient enrollment and IMP demand
            print(f"Patient enrolled on day {env.now}")
        else:
            print(f"Patient drop out on day {env.now}")


def inventory_control(
    env, reorder_point, reorder_quantity, storage_facility, lead_time
):
    """Inventory control process for managing drug stock levels."""
    while True:
        # Check if inventory is below reorder point and order new stock if needed
        if storage_facility.inventory.level < reorder_point:
            print(
                f"Inventory low at day {env.now}, reordering {reorder_quantity} units."
            )
            env.process(place_order(env, storage_facility, reorder_quantity, lead_time))

        # Check inventory stock once a day
        yield env.timeout(1)


def place_order(env, storage_facility, quantity, lead_time):
    """Place an order for additional stock with a certain lead time."""
    # Wait for the lead time before receiving the order
    yield env.timeout(lead_time)

    # Receive the ordered stock
    yield env.process(storage_facility.receive_order(quantity))


def distribute_drug_manufacturer_to_storage(
    env, manufacturer, central_storage, quantity, transit_times
):
    """Simulates the transportation of drugs from the manufacturer to the central storage."""
    yield env.process(manufacturer.produce_drug(quantity))
    yield env.timeout(transit_times["manufacturer_to_central_storage"])

    yield env.process(central_storage.receive_drug(quantity))
    print(
        f"{quantity} units of the drug have been transported from the manufacturer to central storage on day {env.now}."
    )


def distribute_drug_storage_to_storage(
    env, central_storage, regional_storage, quantity, transit_times
):
    """Simulates the transportation of drugs from the central storage to a regional storage."""
    yield central_storage.inventory.get(quantity)
    yield env.timeout(transit_times["central_storage_to_regional_storage"])

    yield env.process(regional_storage.receive_drug(quantity))
    print(
        f"{quantity} units of the drug have been transported from central storage to {regional_storage.name} on day {env.now}."
    )


def plot_inventory_levels(inventory_log, title):
    times, levels = zip(*inventory_log)  # Unzip the log into times and levels
    plt.plot(times, levels, marker="o")
    plt.title(title)
    plt.xlabel("Simulation Time (days)")
    plt.ylabel("Inventory Level (units)")
    plt.grid(True)
    plt.show()


def run_simulation():
    env = simpy.Environment()

    with open("data.yml", "r") as file:
        config = yaml.safe_load(file)["trial_a"]

    # Instantiate resources
    manufacturer = ManufacturingFacility(
        env,
        production_rate=config["manufacturer"]["prod_rate"],
        capacity=config["manufacturer"]["capacity"],
    )
    central_storage = CentralStorageFacility(
        env,
        "central_storage",
        initial_inventory=config["central_storage"]["initial_inventory"],
        capacity=config["central_storage"]["capacity"],
    )
    regional_storage = RegionalStorageFacility(
        env,
        "regional_storage",
        initial_inventory=config["regional_storage"]["initial_inventory"],
        capacity=config["regional_storage"]["capacity"],
    )

    # Define your dosage schedule and trial site here
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

    # Schedule the initial distribution of drugs from manufacturer to central storage
    env.process(
        distribute_drug_manufacturer_to_storage(
            env,
            manufacturer,
            central_storage,
            config["central_storage"]["initial_order"],
            config["transit_times"],
        )
    )

    # Schedule distribution from central storage to regional storage
    env.process(
        distribute_drug_storage_to_storage(
            env,
            central_storage,
            regional_storage,
            config["regional_storage"]["initial_order"],
            config["transit_times"],
        )
    )

    # Start the enrollment process
    env.process(
        patient_enrollment(
            env,
            trial_site,
            config["mean_interarrival_time"],
            config["dropout_rate"],
            config["dosage"],
        )
    )
    # Start production and transportation processes
    env.process(manufacturer.produce_drug(config["manufacturer"]["produce"]))

    env.run(until=config["simulation_time"])  # for example, simulating for one year

    manufacturer_inventory_levels = manufacturer.inventory_log
    central_storage_inventory_levels = central_storage.inventory_log
    regional_storage_inventory_levels = regional_storage.inventory_log
    site_inventory_levels = trial_site.inventory_log

    # Call the plotting function for each facility
    # plot_inventory_levels(
    #     manufacturer_inventory_levels, "Manufacturer Inventory Levels"
    # )
    # plot_inventory_levels(
    #     central_storage_inventory_levels, "Central Storage Inventory Levels"
    # )
    # plot_inventory_levels(
    #     regional_storage_inventory_levels, "Regional Storage Inventory Levels"
    # )
    plot_inventory_levels(site_inventory_levels, "Trial Site Inventory Levels")


run_simulation()
