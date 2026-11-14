# Changelog

## [0.2.0](https://github.com/KB1RMA/ha-protect-watermark/compare/v0.1.1...v0.2.0) (2026-11-14)


### Features

* raise a repair issue when no camera supports the watermark, naming the Protect version and each camera's model and firmware against the minimums (Protect 7.2.98, camera firmware 5.4) ([47ac7b0](https://github.com/KB1RMA/ha-protect-watermark/commit/47ac7b0))


### Bug Fixes

* retry cameras that can't be read yet, such as one that's updating, on each poll and add their entities once they answer, instead of treating them as unsupported until a reload ([9bfd0d5](https://github.com/KB1RMA/ha-protect-watermark/commit/9bfd0d5))
* don't let one unreadable camera hold up the others ([12917e3](https://github.com/KB1RMA/ha-protect-watermark/commit/12917e3))
