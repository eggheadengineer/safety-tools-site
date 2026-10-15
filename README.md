# safety-tools-site

Visual overview of three open-source tools for safety-critical embedded CI, generated from their own output on the reqthread reference project:

- [reqthread](https://github.com/eggheadengineer/reqthread): requirements traceability and certification evidence
- [faultbench](https://github.com/eggheadengineer/faultbench): CAN fault injection with fault-tolerant time interval checks
- [edgegate](https://github.com/eggheadengineer/edgegate): latency, memory, power and accuracy gate for Jetson models and firmware

Live: https://eggheadengineer.github.io/safety-tools-site/

## Regenerate

```
# sibling checkouts of reqthread, faultbench and edgegate
cd ../reqthread/examples/wb55-ref && reqthread build -o /tmp/bundle.json
cd ../../../edgegate && edgegate run -c examples/host/edgegate.yaml -o /tmp/base.json && edgegate run -c examples/host/edgegate.yaml -o /tmp/cand.json
cd ../safety-tools-site && python build.py --bundle /tmp/bundle.json --fb fb.json --make-fb --base /tmp/base.json --cand /tmp/cand.json
```

`template.html` is the page, `build.py` fills in the data, `index.html` is the published result.
