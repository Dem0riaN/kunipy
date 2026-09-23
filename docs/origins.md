# Project origin and provenance

## Current identity

Kunipy began as a Python project based on the ideas and some implementation
material of [Alex2772/kuni](https://github.com/Alex2772/kuni).

The current codebase has moved far beyond a direct port. It contains substantial
new work around:

- Python architecture;
- dependency injection;
- Telegram handling;
- long-term memory;
- diary processing;
- automatic memory formation;
- working memory;
- worker orchestration;
- proactive behaviour;
- proxy functionality;
- metrics;
- desktop-character scaffolding.

For that reason, the project description should say **"inspired by / based on
the original kuni project"** rather than simply **"Python port of kuni"**.

## Upstream license situation

The upstream `kuni` repository did not contain a license at the time the
Kunipy work was started, according to the project history provided by the
maintainer.

This matters legally: absence of a license normally means that copyright
permissions are not automatically granted merely because source code is
publicly visible.

Consequently, the project-specific `LICENSE` in this repository should not be
read as a retroactive license for code that belongs to the upstream author.

## Attribution

Redistributions of Kunipy should retain attribution to:

- Kunipy;
- Dem0riaN;
- Alex2772 / the original `kuni` project where inherited material is
  present.

## Recommended repository wording

Use:

> Kunipy started as a Python project based on the ideas and parts of the
> implementation of Alex2772/kuni. It has since been substantially redesigned
> and extended and is now maintained as an independent Python project.

Avoid:

> Python port of kuni.

That wording understates the amount of new work in the current repository.

## License caution

The custom license in the repository is intentionally conservative about
upstream material. If the intention is to redistribute the entire repository
under a new license, obtain permission from the original copyright holder for
any inherited code for which no license was granted.

This document is a provenance note, not legal advice.
