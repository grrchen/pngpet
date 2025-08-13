# Standard library imports.
import sys
import socket
import configparser

# Related third party imports.

# Local application/library specific imports.

state = sys.argv[1]

config = configparser.ConfigParser()
config.read('states.ini')
try:
    app_config = config["app"]
except KeyError:
    app_config = config["app"] = {
        "hostname": "localhost",
        "port": 8090
    }

host = app_config.get("host", "localhost")
port = int(app_config.get("port", 8090))

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((host, port))
s.send(f"state:{state}".encode("utf-8"))
s.close()
