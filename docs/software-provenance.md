# Software provenance

## Official source

The installer came from the official support page:

- <https://support.amkette.com/software/evofox-blaze-software/>

The page was fetched on 2026-08-26 and returned HTTP `200`. Its HTML identifies the software as **EvoFox Blaze Software**, describes it as compatible with the EvoFox Blaze Programmable Gaming Mouse, and declares Windows as the operating system. It advertises button, lighting, DPI, and firmware settings. Its FAQ names Windows 10 and Windows 11.

At analysis time the page contained two download buttons:

- <https://amkette-media.blr1.digitaloceanspaces.com/nexus-amkette/software/1753439033308.exe>
- <https://amkette-media.blr1.digitaloceanspaces.com/nexus-amkette/software/1753098734587.exe>

Both URLs returned identical content, and both matched the repository file byte-for-byte.

The HTML response also reported:

- Canonical URL: `https://support.amkette.com/software/evofox-blaze-software/`
- Last-Modified header: `Tue, 21 Jul 2026 09:49:50 GMT`
- Page Content-Length: `6657`
- Publisher in JSON-LD: Amkette
- Price in JSON-LD: free

These page details are contextual. The cryptographic hash below is the durable identity for the analyzed installer.

## Repository installer identity

Path:

```text
evofox-blaze.exe
```

Size:

```text
5,243,024 bytes
```

SHA-256:

```text
c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468
```

## Outer executable metadata

Confirmed properties of the installer loader:

- PE32 GUI executable for Intel 80386 / 32-bit Windows.
- Eight PE sections.
- Inno Setup Setup Data version 5.5.7 Unicode.
- Inno Setup Messages version 5.5.3 Unicode.
- The PE loader header timestamp is 2016-04-06; this belongs to the generic installer loader and is not the payload build date.
- The PE contains an Authenticode certificate table.
- Certificate strings identify `Wuxi Yingsite Microelectronics Co., Ltd.` and DigiCert infrastructure. This was observed metadata, not a complete cryptographic signature-validation result.

The signer name is technically relevant, not merely provenance trivia. The official Instant Microelectronics site identifies the same Wuxi Yingsite company, publishes the A825 mouse-controller datasheet, and distributes an A825 reference driver signed under the same English company name. Combined with matching USB IDs and packets, this is strong evidence for an A825-family design. See [Related hardware research](related-hardware-research.md).

## Verification commands

The following read-only commands produced the identity above:

```bash
file evofox-blaze.exe
stat evofox-blaze.exe
sha256sum evofox-blaze.exe
strings -a -n 4 evofox-blaze.exe
objdump -x evofox-blaze.exe
```

## Important qualification

The support page says “firmware settings,” but no standalone firmware image was found in the installer payload. Do not assume that a firmware-update feature exists or is safe to reproduce. Firmware updating is explicitly outside the initial Linux-port scope.
