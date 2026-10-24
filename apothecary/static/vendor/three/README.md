# three.js, kept here rather than fetched

Version 0.160.0, MIT licensed, copied from the package registry. `LICENSE` beside
this file is theirs, unchanged.

## Why a copy

The viewer used to fetch these four files from a public website every time
somebody opened it. That was noted as untidy for a long time. It is worse than
untidy: **with the network switched off the viewer did not work at all** — the
page loaded, the code never arrived, and it sat on "Loading site…" forever. That
was found by a browser test running in a sandbox with no route out, which is the
first thing that ever actually tried it.

Under the proposed rule that the software runs on your machine and keeps your
data there, fetching part of the program from somebody else's server while a
person is using it is a plain break. A copy is the fix, and it is the same fix
whatever the rule ends up saying, because a tool that stops working when a
website changes its mind is not yours.

Four files, about 1.3 MB. Only the parts the viewer imports are here, not the
whole library.

## Updating

Fetch the version you want from the registry and copy the same four paths:

    npm pack three@<version>
    tar xzf three-<version>.tgz
    cp package/build/three.module.js                          three.module.js
    cp package/examples/jsm/controls/OrbitControls.js         addons/controls/
    cp package/examples/jsm/controls/TransformControls.js     addons/controls/
    cp package/examples/jsm/loaders/STLLoader.js              addons/loaders/
    cp package/LICENSE                                        LICENSE

Then check the viewer still opens with the network off.
