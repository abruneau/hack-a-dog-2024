DD_SERVICE="qiskit_app"
DD_ENV="test"
DD_AGENT_HOST="localhost"
# ddtrace-run python app.py
ddtrace-run flask --app app.py --debug run
