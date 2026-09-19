# Reims OS

Reims OS is a minimal Linux appliance for running macOS through QEMU/KVM and Reims VGPU.

## Components

- [felipeab10/reims-vgpu](https://github.com/felipeab10/reims-vgpu)
- [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM)
- [sickcodes/osx-serial-generator](https://github.com/sickcodes/osx-serial-generator)

Dependencies are pinned to validated commits. The appliance never tracks third-party master blindly at runtime; dependency updates require validation and a committed pointer change.

The appliance state model is currently T004 work in progress and remains under validation.
