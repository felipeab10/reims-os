# Reims OS repository split

Source repository: felipeab10/reims-vgpu

Appliance source master: baee3d5c550eb3fb013cc7933f9ff8c2900e1ab1

T004 WIP source: 8b6f873e6fa0d29d0264f52285b5b818a10b34da

Validated historical work:

- T001: persistent launcher
- T002: appliance VM manager, OpenCore per VM, persistent install flow
- T003: native fullscreen integration
- T004: migrated as work in progress; not yet completed

Dependencies at migration:

- reims-vgpu: baee3d5c550eb3fb013cc7933f9ff8c2900e1ab1
- QEMU: bd88218da09b86ed9c78bf5f9354168812a7ba6b
- OSX-KVM: 4c378a4b5e0b219783683012bec680325eb40719
- osx-serial-generator: 908b3d687a200ca6691750fac967670d76f2a17b

Related component work: PR #2 and PR #3 on felipeab10/reims-vgpu. Dependency updates require validation and a committed pointer. Runtime never tracks upstream master blindly.
