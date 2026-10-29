FROM python:3.12-alpine

RUN apk add --no-cache docker-cli docker-cli-compose

WORKDIR /runner
COPY server.py ./server.py

CMD ["python3", "/runner/server.py"]
