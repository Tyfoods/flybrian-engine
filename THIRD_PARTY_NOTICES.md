# Third-party notices

## FlyBody actuator metadata

`flybrian-engine` includes a modified representation of actuator names, declared order, and
MuJoCo-resolved control ranges from the FlyBody fruit-fly model:

- Project: FlyBody
- Upstream repository: https://github.com/TuragaLab/flybody
- Upstream commit: `d015e9bfe441bd90ae431bac24c55cb74bdbce26`
- Source artifact: `flybody/fruitfly/assets/fruitfly.xml`
- Source SHA-256: `d14946fd0311025ecca70c8eeb5de80e1fe18700d3072be37ecbb18d33d80fd8`
- License: Apache License 2.0; see `LICENSES/Apache-2.0.txt`
- Upstream authorship: the FlyBody project credits Google DeepMind and HHMI Janelia Research
  Campus and names its individual package authors in the upstream project metadata

Changes made by FlyBrian contributors:

- extracted the compiled 78-actuator names, order, and resolved `ctrlrange` values into immutable
  Python catalog data;
- added stable catalog identity, body-region/joint labels, control-domain labels, provenance, and
  canonical hashing;
- described the separate FlyBrian historical 90-entry vector as a modified migration profile;
- added explicit aliases for the two historical antenna names; and
- added a named 90-to-78 crosswalk that records the 12 historical `tarsus3`/`tarsus4` values as
  dropped rather than silently truncating or merging them.

The FlyBody XML and other FlyBody source assets are not bundled in this distribution. The
FlyBrian engine's original code remains licensed under MIT as stated in the root `LICENSE`.
