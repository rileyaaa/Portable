# Remaining stable candidate results — 2026-11-26

[Windows run 45732692780](https://github.com/rileyaaa/Portable/actions/runs/45732692780) completed with failure. Actual targeted normal and YOLO Windows consumer acceptance and delivered commits:

- lxml 6.1.3: `d7e1911a67cca5f5b744f6150c110bd7cdbc3bea`
- PyYAML 6.0.4: `e299d0b3039836bae39da04f49562e37dd377dae`
- markdown-it-py 4.3.0: `db7e4947f99b28e8f72eb10f2270de64ee63d739`
- charset-normalizer 3.5.3: `3264d0e869e088a5db92ad129f66bf796e9dcd26`
- Pygments 2.20.0 retained. The verified 2.21.0 wheel installed in staging, but update_locks failed at the exact replacement count assertion before consumer acceptance. Not evidence of runtime incompatibility.

Finalization hit AttributeError: 'NoneType' object has no attribute 'lower' during distribution metadata enumeration. Retire only the expired trigger and staging helper after completion, preserve the delivered commits and reusable consumer tests. No additional refresh or main/tag/Release change. These dev results are not acceptance of the original release ZIP.
