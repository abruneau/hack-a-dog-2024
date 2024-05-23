import flask
import logging
import sys

from tracing import traced_run, traced_transpile

from qiskit import transpile
from qiskit.circuit import QuantumCircuit, QuantumRegister, ClassicalRegister
import qiskit_ibm_runtime
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime.fake_provider import FakeManilaV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import Session, SamplerV2 as Sampler


from ddtrace.vendor import wrapt
import qiskit_ibm_runtime

_fake_run = qiskit_ibm_runtime.fake_provider.fake_backend.FakeBackendV2.run
_run = qiskit_ibm_runtime.IBMBackend.run
_sampler_run = qiskit_ibm_runtime.SamplerV2.run
_transpile = transpile
_job = qiskit_ibm_runtime.QiskitRuntimeService.job
# _stream_results = qiskit_ibm_runtime.RuntimeJobV2.stream_results

qiskit_ibm_runtime.fake_provider.fake_backend.FakeBackendV2.run = wrapt.FunctionWrapper(
    _fake_run, traced_run
)
qiskit_ibm_runtime.IBMBackend.run = wrapt.FunctionWrapper(_run, traced_run)
qiskit_ibm_runtime.SamplerV2.run = wrapt.FunctionWrapper(_sampler_run, traced_run)
qiskit_ibm_runtime.QiskitRuntimeService.job = wrapt.FunctionWrapper(_job, traced_run)
transpile = wrapt.FunctionWrapper(_transpile, traced_transpile)
# qiskit_ibm_runtime.base_runtime_job.BaseRuntimeJob._stream_results = wrapt.FunctionWrapper(qiskit_ibm_runtime.base_runtime_job.BaseRuntimeJob._stream_results, traced_base_runtime_job_stream_results)
# qiskit_ibm_runtime.RuntimeJobV2.stream_results = wrapt.FunctionWrapper(_stream_results, traced_stream_results)
# qiskit_ibm_runtime.RuntimeJob.stream_results = wrapt.FunctionWrapper(qiskit_ibm_runtime.RuntimeJob.stream_results, traced_stream_results)

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
app = flask.Flask(__name__)
app.config["INFO"] = True


token = open("ibmapi.txt", "r").read()
# Save an IBM Cloud account.
QiskitRuntimeService.save_account(
    channel="ibm_quantum",
    token=token,
    set_as_default=True,
    instance="ibm-q/open/main",
    overwrite=True,
)
service = QiskitRuntimeService()

# Bell Circuit
qr = QuantumRegister(2, name="qr")
cr = ClassicalRegister(2, name="cr")
qc = QuantumCircuit(qr, cr, name="bell")
qc.h(qr[0])
qc.cx(qr[0], qr[1])
qc.measure(qr, cr)


@app.route("/simulate", methods=["GET"])
def simul():
    backend = FakeManilaV2()
    # Create a Sampler object
    # Transpile the ideal circuit to a circuit that can be directly executed by the backend
    transpiled_circuit = transpile(qc, backend)
    # Submit the circuit to the sampler
    job = backend.run(transpiled_circuit)
    return job.result().status


@app.route("/run", methods=["GET"])
def run():
    backend = service.least_busy(simulator=False, operational=True, min_num_qubits=5)
    transpiled_circuit = transpile(qc, backend)
    job = backend.run(transpiled_circuit)
    job.stream_results(log_results)
    return "OK"

@app.route("/session", methods=["GET"])
def session():
    backend = service.least_busy(simulator=False, operational=True, min_num_qubits=5)
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa_circuit = pm.run(qc)
    with Session(backend=backend) as session:
        sampler = Sampler(session=session)
        job = sampler.run([isa_circuit])
        log_results(job.job_id(), job.result())
        # pub_result = job.result()[0]
        # print(f"Sampler job ID: {job.job_id()}")
        # logging.info(pub_result)
        # print(f"Counts: {pub_result.data.cr.get_counts()}")
    return "OK"

@app.route("/replay/<jobid>", methods=["GET"])
def replay(jobid):
    job = service.job(jobid)
    # span = _start_span_with_tags(job)
    # _close_span_on_success(job, span)
    # job.stream_results(log_results)
    log_results(jobid, job.result())
    return "OK"

def log_results(job_id, result):
    logging.info(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
