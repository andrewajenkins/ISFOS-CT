import simpy
import random
import yaml


class ManufacturingFacility:
    def __init__(self, env, production_rate, capacity):
        self.env = env
        self.production_rate = production_rate  # units per day
        self.capacity = simpy.Container(
            env, init=0, capacity=capacity
        )  # represents the on-hand inventory of drugs

    def produce_drug(self, quantity):
        """Simulates the production of the drug."""
        production_time = quantity / self.production_rate
        yield self.env.timeout(
            production_time
        )  # Simulates the passage of production time
        yield self.capacity.put(
            quantity
        )  # Add the produced drugs to the facility's inventory
        print(f"Produced {quantity} units of the drug.")


class StorageFacility:
    def __init__(self, env, name, initial_inventory, capacity):
        self.env = env
        self.name = name
        self.inventory = simpy.Container(
            env, init=initial_inventory, capacity=capacity
        )  # Drug inventory

    def order_drug(self, quantity):
        """Processes an order and waits if necessary for stock to be available."""
        yield self.inventory.get(quantity)
        print(f"Order fulfilled for {quantity} units of the drug.")

    def receive_drug(self, quantity):
        """Receives a shipment of drugs and adds it to the inventory."""
        yield self.inventory.put(quantity)
        print(f"Received an order of {quantity} units of the drug. {self.env.now}")

    def dispatch_drug(self, quantity):
        """Dispatch drugs for transportation."""
        yield self.inventory.get(quantity)
        print(f"Dispatched {quantity} units for drug on day {self.env.now}.")


# Subclass for RegionalStorageFacility
class RegionalStorageFacility(StorageFacility):
    def __init__(self, env, name, initial_inventory, capacity):
        super().__init__(env, name, initial_inventory, capacity)


# Subclass for CentralStorageFacility
class CentralStorageFacility(StorageFacility):
    def __init__(self, env, name, initial_inventory, capacity):
        super().__init__(env, name, initial_inventory, capacity)


class TrialSite:
    def __init__(self, env, dosage_schedule, capacity):
        self.env = env
        self.patients = 0
        self.dosage_schedule = dosage_schedule  # Dosage per patient
        self.inventory = simpy.Container(env, init=0, capacity=capacity)

    def request_resupply(self, storage_facility, quantity):
        """Requests a resupply of drugs from a storage facility."""
        self.env.process(storage_facility.order_drug(quantity))
        print(f"Requested resupply of {quantity} units of the drug.")

    def receive_drug(self, quantity):
        """Receives a shipment of drugs."""
        yield self.inventory.put(quantity)
        print(f"Trial site received {quantity} units of the drug.")

    def enroll_patient(self):
        """Handle the logistics of enrolling a new patient."""
        self.patients += 1
        dosage_schedule = DosageSchedule(dose_amount=50, dose_interval=7)
        self.env.process(
            self.patient_demand(dosage_schedule)
        )  # Start the demand process for the new patient

    def patient_demand(self, dosage_schedule):
        """Simulates the drug demand for an individual patient."""
        while True:
            # Wait until the next dosage is due
            yield self.env.timeout(dosage_schedule.get_next_dose_time())

            # Consume drug and generate demand
            self.consume_drug(dosage_schedule.next_dose())
            print(f"Drug consumed by patient on day {self.env.now}")

    def consume_drug(self, amount):
        """Logic to consume drug and potentially trigger resupply."""
        # This would interact with inventory management
        pass

    def receive_drug(self, quantity):
        """Receives a shipment of drugs."""
        yield self.inventory.put(quantity)
        print(f"Received {quantity} units of drug on day {self.env.now}.")


class DosageSchedule:
    def __init__(self, dose_amount, dose_interval):
        """
        Initializes the dosage schedule for a patient.

        :param dose_amount: The amount of drug administered in each dose.
        :param dose_interval: The time interval between doses in days.
        """
        self.dose_amount = dose_amount
        self.dose_interval = dose_interval
        self.next_dose_time = 0  # Tracks the time until the next dose for a patient

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


def patient_enrollment(env, trial_site, mean_interarrival_time, dropout_rate):
    """Simulates patient enrollment over time."""
    while True:
        # Simulate the time until the next patient enrollment
        interarrival_time = random.expovariate(1.0 / mean_interarrival_time)

        # Wait for the next enrollment event
        yield env.timeout(interarrival_time)

        # Enroll the patient
        if random.random() >= dropout_rate:
            trial_site.enroll_patient()  # Add logic to handle patient enrollment and IMP demand
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
    trial_site = TrialSite(env, dosage_schedule, capacity=config["site"]["capacity"])

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
            env, trial_site, config["mean_interarrival_time"], config["dropout_rate"]
        )
    )
    # Start production and transportation processes
    env.process(manufacturer.produce_drug(config["manufacturer"]["produce"]))

    env.run(until=config["simulation_time"])  # for example, simulating for one year


run_simulation()
