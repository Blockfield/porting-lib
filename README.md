# Porting Lib — зеркало артефактов

Mirror of the [Porting Lib](https://github.com/Fabricators-of-Create/Porting-Lib) modules used by the Blockfield builds. The source project is maintained by Fabricators of Create.

Unmodified JARs live in Releases; no mod binaries are committed. This mirror does not relicense upstream.

## Описание релиза

Файл `release-notes/<тег>.md` хранится в этом репозитории. Его содержимое используется
как тело GitHub Release и как вложение `release-notes.md`.
[Формат и подготовка](https://github.com/Blockfield/blockfield-client/blob/main/docs/RELEASE-NOTES.md)
описаны в клиентском репозитории; используйте его `scripts/release-notes-tool.py`
из проверенного клона для команд `skeleton` и `check` с параметрами
`--repository Blockfield/porting-lib`, `--version <тег>` и `--kind resource`.
Укажите `backfilled: false`, а в `previous_version` — последнюю опубликованную
версию этой линии.

Публикуйте новый артефакт с контрольными суммами и описанием; старые релизы
не перезаписывайте. После выпуска обновите соответствующие пины сборки.

## Developer checks

Install Python 3.12+, Node.js 22 and Just 1.57.0 on Linux or Windows. Quality tools stay in the project cache.

```sh
just setup
just check
just format
```

`just --list` lists supported build and application commands.

Условия использования: [LICENSE](LICENSE).
