# Reims OS

Reims OS is a minimal Linux appliance for running macOS through QEMU/KVM and Reims VGPU.

## Components

- [felipeab10/reims-vgpu](https://github.com/felipeab10/reims-vgpu)
- [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM)
- [sickcodes/osx-serial-generator](https://github.com/sickcodes/osx-serial-generator)

Dependencies are pinned to validated commits. The appliance never tracks third-party master blindly at runtime; dependency updates require validation and a committed pointer change.

## Development bootstrap

Use the selective bootstrap; do not run a blind recursive submodule update. Reims OS owns the canonical OSX-KVM and serial-generator checkouts, while historical copies inside reims-vgpu remain uninitialized.

```bash
git clone https://github.com/felipeab10/reims-os.git
cd reims-os
./scripts/bootstrap-deps.sh
```

The bootstrap pins Reims VGPU, its QEMU source, OSX-KVM, and osx-serial-generator. QEMU firmware and test submodules are lazy/on-demand and are not materialized automatically.

The appliance state model is currently T004 work in progress and remains under validation.
