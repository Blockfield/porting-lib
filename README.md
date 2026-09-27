# Porting Lib — pinned Blockfield dependencies

Private artifact mirror of the exact dependencies previously vendored by the modpack. Upstream: https://github.com/Fabricators-of-Create/Porting-Lib

Unmodified JARs live in Releases; no mod binaries are committed. This mirror does not relicense upstream.

## Описание релиза (release-notes.md)

Каждый новый релиз публикуется с описанием в едином формате Blockfield: тело релиза и asset `release-notes.md` — один и тот же файл `release-notes/<тег>.md`, закоммиченный в этот репозиторий. Инструмент проверки общий, из `Blockfield/blockfield-client`:

```sh
mkdir -p release-notes rn
gh api repos/Blockfield/blockfield-client/contents/scripts/release-notes-tool.py \
  -H 'Accept: application/vnd.github.raw' > rn/release-notes-tool.py
python3 rn/release-notes-tool.py skeleton --repository Blockfield/porting-lib --version <тег> \
  --previous-version <прошлый тег> --kind resource --date YYYY-MM-DD > release-notes/<тег>.md
# заполните разделы по коммитам и изменениям рецепта; чего не знаете — отметьте в «Источниках»
python3 rn/release-notes-tool.py check release-notes/<тег>.md \
  --repository Blockfield/porting-lib --version <тег> --kind resource
cp release-notes/<тег>.md rn/release-notes.md
gh release create <тег> <артефакты> SHA256SUMS rn/release-notes.md \
  --notes-file rn/release-notes.md --repo Blockfield/porting-lib
```

Если `check` выводит ошибки, релиз не публикуйте. После выпуска обновите пин в клиенте/сервере; их релизные описания подтянут этот файл в раздел «Обновлённые компоненты».
