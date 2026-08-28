# Local deployment

`compose.yaml` builds the locked web and control-plane sources and exposes the
complete product at `http://127.0.0.1:8088`.

From the repository root:

```bash
just run
```

Set `CORAL_CITY_WEB_PORT` when 8088 is occupied. The control plane is reachable
only through the web ingress; it is not published directly to the host.
