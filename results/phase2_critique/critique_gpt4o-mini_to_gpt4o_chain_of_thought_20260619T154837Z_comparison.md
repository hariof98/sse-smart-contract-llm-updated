# Phase 2 — Detector vs Critic comparison

Source: `critique_gpt4o-mini_to_gpt4o_chain_of_thought_20260619T154837Z.json`  
Tool: `critique_gpt4o-mini_to_gpt4o_chain_of_thought`

## Summary

- Contracts evaluated: **54**  (with a real vulnerability: 54)
- Exactly-correct contracts: detector **5/54** -> after-critic **33/54**
- Pipeline errors: critic failed on **9** (fell back to detector output), detector failed on **1**
- Per-contract effect of the critic: helped **29**, hurt **0**, mixed **4**, no change **21**

> Note: the `critic failed` contracts could not be revised, so their
> 'after-critic' value equals the detector value. The true effect of
> critique is best read on the contracts where it actually ran.

## Metrics before vs after critique



| Class                  |             Detector |         After-Critic |     ΔF1 |
|                        |      P      R     F1 |      P      R     F1 |         |
|------------------------|----------------------|----------------------|---------|
| reentrancy             |  0.625  0.968  0.759 |  0.879  0.935  0.906 |  +0.147 |
| access_control         |  0.353  1.000  0.522 |  0.533  0.889  0.667 |  +0.145 |
| timestamp_dependency   |  0.714  1.000  0.833 |  0.714  1.000  0.833 |    ·    |
|------------------------|----------------------|----------------------|---------|
| micro-average          |  0.500  0.981  0.663 |  0.714  0.926  0.806 |  +0.144 |
| macro-average          |  0.564  0.989  0.705 |  0.709  0.941  0.802 |  +0.097 |

Confusion counts (Detector -> After-Critic)

| Class                  |        TP |        FP |        FN |
|------------------------|-----------|-----------|-----------|
| reentrancy             |  30 -> 29  |  18 -> 4   |   1 -> 2   |
| access_control         |  18 -> 16  |  33 -> 14  |   0 -> 2   |
| timestamp_dependency   |   5 -> 5   |   2 -> 2   |   0 -> 0   |
|------------------------|-----------|-----------|-----------|
| TOTAL (micro)          |  53 -> 50  |  53 -> 20  |   1 -> 4   |

## Per-contract breakdown

| # | Contract | Actual | Detector | det✓ | After-Critic | crit✓ | Removed | Added | Effect |
|--:|---|---|---|:--:|---|:--:|---|---|---|
| 1 | `access_control/FibonacciBalance.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 2 | `access_control/arbitrary_location_write_simple.sol` | access_control | access_control | ✓ | access_control | ✓ | · | · | same |
| 3 | `access_control/incorrect_constructor_name1.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 4 | `access_control/incorrect_constructor_name2.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 5 | `access_control/incorrect_constructor_name3.sol` | access_control | access_control|reentrancy | ✗ | (none) | ✗ | access_control|reentrancy | · | mixed |
| 6 | `access_control/mapping_write.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 7 | `access_control/multiowned_vulnerable.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 8 | `access_control/mycontract.sol` | access_control | access_control | ✓ | access_control | ✓ | · | · | same |
| 9 | `access_control/parity_wallet_bug_1.sol` | access_control | access_control|reentrancy|timestamp_dependency | ✗ | access_control | ✓ | reentrancy|timestamp_dependency | · | helped |
| 10 | `access_control/parity_wallet_bug_2.sol` | access_control | access_control|reentrancy | ✗ | (none) | ✗ | access_control|reentrancy | · | mixed |
| 11 | `access_control/phishable.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 12 | `access_control/proxy.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 13 | `access_control/rubixi.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 14 | `access_control/simple_suicide.sol` | access_control | access_control | ✓ | access_control | ✓ | · | · | same |
| 15 | `access_control/unprotected0.sol` | access_control | access_control | ✓ | access_control | ✓ | · | · | same |
| 16 | `access_control/wallet_02_refund_nosub.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 17 | `access_control/wallet_03_wrong_constructor.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 18 | `access_control/wallet_04_confused_sign.sol` | access_control | access_control|reentrancy | ✗ | access_control | ✓ | reentrancy | · | helped |
| 19 | `reentrancy/0x01f8c4e3fa3edeb29e514cba738d87ce8c091d3f.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 20 | `reentrancy/0x23a91059fdc9579a9fbd0edc5f2ea0bfdb70deb4.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 21 | `reentrancy/0x4320e6f8c05b27ab4707cd1f6d5ce6f3e4b3a5a1.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 22 | `reentrancy/0x4e73b32ed6c35f570686b89848e5f39f20ecc106.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 23 | `reentrancy/0x561eac93c92360949ab1f1403323e6db345cbf31.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 24 | `reentrancy/0x627fa62ccbb1c1b04ffaecd72a53e37fc0e17839.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 25 | `reentrancy/0x7541b76cb60f4c60af330c208b0623b7f54bf615.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy|timestamp_dependency | ✗ | access_control | timestamp_dependency | mixed |
| 26 | `reentrancy/0x7a8721a9d64c74da899424c1b52acbf58ddc9782.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 27 | `reentrancy/0x7b368c4e805c3870b6c49a3f1f49f69af8662cf3.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 28 | `reentrancy/0x8c7777c45481dba411450c228cb692ac3d550344.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 29 | `reentrancy/0x93c32845fae42c83a70e5f06214c8433665c2ab5.sol` | reentrancy | access_control|reentrancy|timestamp_dependency | ✗ | reentrancy|timestamp_dependency | ✗ | access_control | · | helped |
| 30 | `reentrancy/0x941d225236464a25eb18076df7da6a91d0f95e9e.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 31 | `reentrancy/0x96edbe868531bd23a6c05e9d0c424ea64fb1b78b.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 32 | `reentrancy/0xaae1f51cf3339f18b6d3f3bdc75a5facd744b0b8.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 33 | `reentrancy/0xb5e1b1ee15c6fa0e48fce100125569d430f1bd12.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 34 | `reentrancy/0xb93430ce38ac4a6bb47fb1fc085ea669353fd89e.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 35 | `reentrancy/0xbaf51e761510c1a11bf48dd87c0307ac8a8c8a4f.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 36 | `reentrancy/0xbe4041d55db380c5ae9d4a9b9703f1ed4e7e3888.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same |
| 37 | `reentrancy/0xcead721ef5b11f1a7b530171aab69b16c5e66b6e.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 38 | `reentrancy/0xf015c35649c82f5467c9c74b7f28ee67665aad68.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 39 | `reentrancy/etherbank.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 40 | `reentrancy/etherstore.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 41 | `reentrancy/modifier_reentrancy.sol` | reentrancy | access_control|reentrancy | ✗ | (none) | ✗ | access_control|reentrancy | · | mixed |
| 42 | `reentrancy/reentrance.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 43 | `reentrancy/reentrancy_bonus.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 44 | `reentrancy/reentrancy_cross_function.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 45 | `reentrancy/reentrancy_dao.sol` | reentrancy | access_control|reentrancy | ✗ | reentrancy | ✓ | access_control | · | helped |
| 46 | `reentrancy/reentrancy_insecure.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same ⚠ |
| 47 | `reentrancy/reentrancy_simple.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same ⚠ |
| 48 | `reentrancy/simple_dao.sol` | reentrancy | access_control|reentrancy | ✗ | access_control|reentrancy | ✗ | · | · | same ⚠ |
| 49 | `reentrancy/spank_chain_payment.sol` | reentrancy | (none) | ✗ | (none) | ✗ | · | · | same ⚠ |
| 50 | `time_manipulation/ether_lotto.sol` | timestamp_dependency | reentrancy|timestamp_dependency | ✗ | reentrancy|timestamp_dependency | ✗ | · | · | same ⚠ |
| 51 | `time_manipulation/governmental_survey.sol` | timestamp_dependency | access_control|reentrancy|timestamp_dependency | ✗ | access_control|reentrancy|timestamp_dependency | ✗ | · | · | same ⚠ |
| 52 | `time_manipulation/lottopollo.sol` | timestamp_dependency | access_control|reentrancy|timestamp_dependency | ✗ | access_control|reentrancy|timestamp_dependency | ✗ | · | · | same ⚠ |
| 53 | `time_manipulation/roulette.sol` | timestamp_dependency | access_control|reentrancy|timestamp_dependency | ✗ | access_control|reentrancy|timestamp_dependency | ✗ | · | · | same ⚠ |
| 54 | `time_manipulation/timed_crowdsale.sol` | timestamp_dependency | timestamp_dependency | ✓ | timestamp_dependency | ✓ | · | · | same ⚠ |

Legend: det✓ / crit✓ = prediction exactly matches ground truth. ⚠ = critic call failed (after-critic = detector fallback).
