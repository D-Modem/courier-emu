# Courier 3453 regional models: confirmed IDs versus country profiles

## Manufacturer-documented variants

USR's current [3453C support page](https://www.usr.com/support/usr3453c/)
lists **USR3453C, USR843453C, USR813453C**. Its identification instructions
accept bottom-label product numbers **64-003453-02R** and **64-993453-02R**.
The same numbers **without R** are described as no longer supported.

These are three different identifier namespaces:

| Identifier | Meaning / evidence |
|---|---|
| `USR3453C` | North-American sales code on the official product page |
| `USR843453C` | EMEA sales code in the official global accessory/approval guide |
| `USR813453C` | Additional sales code explicitly listed on the C support page; precise regional packaging mapping not established by the examined sources |
| `USR3453C-REF` | Refurbished offering; separately listed product/support page |
| `64-003453-02R`, `64-993453-02R` | Bottom-label product numbers accepted by C support instructions |
| `64-003453-02`, `64-993453-02` | Older, non-R label numbers distinguished by those instructions |
| `00345303`, `99345303` | Eight-character IDs recovered from B/C and C settings / ATI7; not the same suffix scheme as bottom-label numbers |

Do **not** interpret sales prefix `84`, label prefix `99`, country-table index
`08`, and a PCB revision suffix as interchangeable encodings.

The C support page explicitly warns that its firmware is **not compatible
with non-RoHS USR3453B or 3CP3453**. This is a real family distinction, not a
reason to load a regional firmware indiscriminately. The manufacturer's
2.3.33 release notes list **2.2.09 as Original Release**, so a 2.2.09 version
number alone is not proof that a modem is a legacy B rather than an early C
or the observed hybrid. The separately captured DSP/code hashes and board
components remain important.

The refurbished page calls `USR3453C-REF` a recommended replacement but warns
that features/specifications vary. Its support page offers the C 2.3.33
firmware. We have not inspected a REF board and do not infer identical parts
or memory geometry.

## What CTR21 means here

CTR21 is the pan-European telephone-line profile/approval, **not a fourth
PCB revision or a distinct DSP RAM capacity**. The C declaration of
conformity identifies the model family as `USRxx3453C`, equipment as
`USR COURIER V.92 EURO-ROHS2`, and lists **TBR21** among its standards.
The firmware names its corresponding country profile **CTR21**, index 8.

The manufacturer's global guide markets one hardware platform with
V.Everywhere and country accessories. It lists approvals/support for more
than 75 countries, much more than the firmware's 28 table entries. Neither
number is a count of distinct PCB models.

### Direct evidence: country selection does not change manufacturing ID

Existing hardware capture:
`artifacts/3453c-board-identity-20261003/country-set-us.txt`.

After the historical `AT~C#0` RAM-profile selection:

```
Product type           US/Canada External
Product ID             99345303
```

The board was originally CTR21. Thus `99` is **not** computed from the active
country index each time ATI7 runs. This transcript is historical evidence;
no new hardware setting command was issued for this investigation.

All four CRC-valid captured C parameter sectors (versions 57–60) contain
country byte `08` at offset `0001` and ASCII `99345303` at offset `0E3A`.
Those are independent stored fields. In normal firmware the product override
getter has no country-table lookup: it prints the stored string, or selects
fixed `00345303` / `XX345303` fallback literals when the first byte is zero.
No 28-entry manufacturing-prefix generator has been found.

## Actual firmware regional profiles

The captured B/C and C supervisors each contain 28 records, 128 bytes each:

| Index | Profile | Index | Profile |
|---:|---|---:|---|
| 00 | US/Canada | 14 | Indonesia |
| 01 | UK | 15 | Korea |
| 02 | Germany | 16 | Malaysia |
| 03 | Italy | 17 | Mexico |
| 04 | France | 18 | New Zealand |
| 05 | Russia | 19 | Poland |
| 06 | Japan | 20 | Romania |
| 07 | Australia | 21 | Singapore |
| 08 | CTR21 | 22 | South Africa |
| 09 | Brazil | 23 | Taiwan |
| 10 | China | 24 | Argentina |
| 11 | Czech Rep | 25 | India |
| 12 | Hong Kong | 26 | Bulgaria |
| 13 | Hungary | 27 | Turkey |

These have real line-parameter differences. For example the Si3034 fields
at record offsets `79`, `7A`, `7B` are:

| Profile | Register 16 | Register 17 table | Register 17 sent (`& FB`) | Register 18 |
|---|---:|---:|---:|---:|
| US/Canada | `28` | `A0` | `A0` | `02` |
| UK | `2C` | `B8` | `B8` | `02` |
| CTR21 | `2C` | `BC` | `B8` | `02` |

The UK and CTR21 records therefore are not simply two different SKU strings;
although the sent codec bytes match, other ring/timing/profile fields can
differ. Full record hashes, names, offsets and these register fields are
published in the audit JSON. No physical country-profile change is needed
to inspect them.

## Accessories are not extra modem revisions

The official global-kit guide lists:

* `USR013453A-ACC`: UK phone adapter / power cord kit.
* `USR043453A-ACC`: Australian power cord and adapters.
* `USR053453A-ACC`: Korean/Argentine/Brazilian power accessories.
* `USR243453A-ACC`: German/Italian/French phone adapters and Euro power cord.
* `USR563453A-ACC`: Euro power cord / loopback / dongle kit.
* `USR723453A-ACC`: India/South Africa power cord and UK phone adapter.
* `USR3453CIEC-ACC`: IEC power-cord conversion accessories.

An `A` in one of these accessory numbers does **not** identify a 3453A modem
PCB. Their numeric prefixes are not a demonstrated ATI7 prefix mapping.

## Sources and reproducibility

Manufacturer pages examined (public HTTP reads only):

* https://www.usr.com/support/usr3453c/
* https://www.usr.com/products/56k-dialup-modem/usr3453c/
* https://www.usr.com/products/usr3453c-ref/
* https://www.usr.com/support/usr3453c-ref/
* https://www.usr.com/education/courier-global-kits/
* https://www.usr.com/assets/CE_USRXX3453C.pdf
* https://support.usr.com/support/3453c/3453c-files/USR3453C_v2.3.33-ReleaseNotes.txt

Source excerpts / curated findings:
`artifacts/3453-product-ram-audit-20261014/regional-model-sources.json`.
Country-table extraction: `tools/audit_3453_product_ids.py IMAGE...`.

Remaining unknown: exhaustive historical sales SKUs and factory prefix rules,
exact regional packaging of `USR813453C`, and electrical differences among
all national approvals. No numeric regional manufacturing prefix has been
invented from country-table order.
