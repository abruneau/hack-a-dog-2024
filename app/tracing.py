from ddtrace import tracer
import time
import logging
import sys
import ddtrace
from qiskit_ibm_runtime import RuntimeJob, RuntimeJobV2
from qiskit.primitives import PrimitiveResult
from ddtrace.vendor import wrapt
from qiskit.result import Result
from qiskit.providers.exceptions import JobTimeoutError
from qiskit.providers.jobstatus import JOB_FINAL_STATES
from typing import Optional
import threading
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

job_spans = {}
job_start_time = {}

START_TIME = "_ddtrace_job_start_time"


def traced_run(func, _, args, kwargs):
    job = func(*args, **kwargs)
    try:
        span = _start_span_with_tags(job)
        stream_thread = threading.Thread(target=stream_result, args=[job, span])
        stream_thread.start()
        if isinstance(job, RuntimeJob) or isinstance(job, RuntimeJobV2):
            job.stream_results = wrapt.FunctionWrapper(
                job.stream_results, traced_stream_results
            )

    except Exception:
        span.set_exc_info(*sys.exc_info())
    return job

def traced_stream_results(func, _, args, kwargs):
    logging.info("traced_stream_results")
    callback = args[0]
    def traced_callback(*args, **kwargs):
        logging.info("traced_stream_results_callback")
        return callback(*args, **kwargs)
    return func(traced_callback, *args[1:], **kwargs)

# def traced_stream_results_callback(func, _, args, kwargs):
#     logging.info("traced_stream_results_callback")
#     return func(*args, **kwargs)

def _start_span_with_tags(job):
    span = tracer.trace("qiskit.job")
    start_time = time.time()
    job_id = job.job_id()
    span.set_tag("job.start_time", start_time)
    setattr(job, START_TIME, start_time)
    span.set_tag("job.id", job_id)
    back = job.backend()
    span.set_tag("job.backend.name", back.name)
    span.set_tag("job.backend.provider", back.provider)
    span.set_tag("job.backend.version", back.version)
    if isinstance(job, RuntimeJobV2):
        span.set_tag("job.session_id", job.session_id)
        span.set_tag("job.program_id", job.program_id)
    if isinstance(job, RuntimeJob):
        span.set_tag("job.session_id", job.session_id)
        span.set_tag("job.program_id", job.program_id)
        span.set_tag("job.queue_position", job.queue_position(refresh=False))
    return span

def traced_transpile(func, _, args, kwargs):
    with tracer.trace("qiskit.transpile"):
        return func(*args, **kwargs)

def _close_span_on_success(job, span: ddtrace.Span):
    try:
        span.set_tag("job.status", job.status())
        stop_time = time.time()
        result = job.result()
        logging.info(result)
        if isinstance(result, Result):
            span.set_tag("job.shots", getattr(result.results[0], "shots", 0))
            span.set_tag("job.name", getattr(result.results[0], "name", ""))
            span.set_tag("job.duration", result.time_taken)
        elapsed_time = stop_time - getattr(job, START_TIME) - result.time_taken
        if elapsed_time < 0:
            elapsed_time = 0
        span.set_tag("job.wait_time", elapsed_time)
    except Exception:
        logging.debug("an exception occurred while setting tags", exc_info=True)
    finally:
        span.finish()
        delattr(job, START_TIME)

# def _close_span_on_error(job, span: ddtrace.Span):
#     span.set_tag("job.status", job.status())
#     try:
#         # handling the exception manually because we
#         # don't have an ongoing exception here
#         span.error = 1
#         span.set_tag_str(ERROR_MSG, exc.args[0])
#         span.set_tag_str(ERROR_TYPE, exc.__class__.__name__)
#     except Exception:
#         log.debug("traced_set_final_exception was not able to set the error, failed with error", exc_info=True)
#     finally:
#         span.finish()
#         delattr(future, CURRENT_SPAN)
#     span.finish()


def stream_result(job, span: ddtrace.Span, timeout: Optional[float] = None, wait: float = 5):
    """Poll the job status until it progresses to a final state such as ``DONE`` or ``ERROR``.

    Args:
        job: the job to look for
        span: the job span
        timeout: Seconds to wait for the job. If ``None``, wait indefinitely.
        wait: Seconds between queries.

    Raises:
        JobTimeoutError: If the job does not reach a final state before the
            specified timeout.
    """
    logging.info("Waiting for job to finish")
    start_time = time.time()
    status = job.status()
    while status not in JOB_FINAL_STATES:
        logging.info(status)
        elapsed_time = time.time() - start_time
        if timeout is not None and elapsed_time >= timeout:
            raise JobTimeoutError(f"Timeout while waiting for job {job.job_id()}.")
        time.sleep(wait)
        status = job.status()
    _close_span_on_success(job, span)
    return