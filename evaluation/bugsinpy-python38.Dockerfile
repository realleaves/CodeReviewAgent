FROM python:3.8-slim@sha256:1d52838af602b4b5a831beb13a0e4d073280665ea7be7f69ce2382f29c5a613f
COPY evaluation/bugsinpy-python38-requirements.txt /tmp/test-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/test-requirements.txt
