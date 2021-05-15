#!/usr/bin/env python
import datetime as dt
import json
import socket
import sys


def main():
    machine = sys.argv[1]
    build = int(sys.argv[2])
    date = dt.datetime.now(dt.timezone.utc)
    hostname = socket.gethostname()
    print(
        json.dumps(
            {
                "machine": machine,
                "build": build,
                "date": date.isoformat(),
                "buildHost": hostname,
            }
        )
    )


if __name__ == "__main__":
    main()
