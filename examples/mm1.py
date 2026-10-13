from simcore import *

m = Model("M/M/1", time_units="minutes")
m.resource("Server", capacity=1)
m.add(
    Create(interval="EXPO(1.0)", entity_type="Customer"),
    Queue("Server.Queue"),
    Seize(resources=[("Server", 1)]),
    Delay(duration="EXPO(0.8)", allocation="value_added"),
    Release(resources=[("Server", 1)]),
    Count(counter="Served"),
    Dispose(),
)
m.replicate(replications=5, length=50_000)

if __name__ == "__main__":
    res = m.run()
    print(res.report().split("=== Replication 2")[0])
    for p in ["queues.Server.Queue.waiting_time.average",
              "queues.Server.Queue.number_waiting.average",
              "resources.Server.instantaneous_utilization"]:
        a = res.across(p)
        print(f"{p:50s} {a['average']:.4f} ± {a['half_width']:.4f}")
