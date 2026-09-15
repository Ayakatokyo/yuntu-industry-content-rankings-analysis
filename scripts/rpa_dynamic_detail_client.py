#!/usr/bin/env python3
"""Dynamic-parameter entrypoint for Yuntu material details."""

import rpa_dynamic_client as runtime


CONNECTOR_CODE = "rpa.conn.juliang.yt.industry.content.rankings.details"


def main():
    runtime.CONNECTOR_CODE = CONNECTOR_CODE
    return runtime.main()


if __name__ == "__main__":
    raise SystemExit(main())
