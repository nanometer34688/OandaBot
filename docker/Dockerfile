FROM alpine:3.14

RUN mkdir -p /home/OandaBot
WORKDIR /home/OandaBot

COPY . /home/OandaBot
RUN apk update && apk add bash
# Install python/pip
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools

RUN pip3 install -r requirements.txt

CMD ["/bin/sh"]