#!/usr/bin/env python3
"""Пересобрать files/mods/*-bf1.jar из опубликованных релизов Blockfield.

porting_lib_loot: пустой статический реестр
porting_lib:global_loot_modifier_serializers ванила в BuiltInRegistries.validate
считает пустым -- ERROR "was empty after loading" на старте. Ни один мод пака не
регистрирует сериализаторы и не поставляет GLM-датапак (проверено сканом всех
jar'ов обеих сторон). PatchPortingLib.java заменяет создание реестра через
PortingLib RegistryBuilder.create() (SimpleRegistry + регистрация в корневой
карте) на отдельный SimpleRegistry вне корневой карты: поле не-null, тип и
поведение кода не меняются, валидация его не видит.

add: новые записи, дописываемые в jar (формат "entry: текст файла").
patch_bytes: байтовые замены в бинарных записях (class), каждая обязана сработать раз.
Ровность соответствий проверяется: если замена ни разу не сработала, сборка падает.
Для сборки нужен JDK 21 (javac компилирует трансформер).
Запуск из корня репозитория: python3 -I scripts/patch.py
"""

import fnmatch
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from toolchain import child_env  # noqa: E402 — isolated Python omits the script directory.

ASM_VERSION = "9.8"
ASM_SHA256 = {
    "asm": "876eab6a83daecad5ca67eb9fcabb063c97b5aeb8cf1fca7a989ecde17522051",
    "asm-tree": "14b7880cb7c85eed101e2710432fc3ffb83275532a6a894dc4c4095d49ad59f1",
    "asm-analysis": "e640732fbcd3c6271925a504f125e38384688f4dfbbf92c8622dfcee0d09edb9",
    "asm-util": "8ba0460ecb28fd0e2980e5f3ef3433a513a457bc077f81a53bdc75b587a08d15",
}

JARS = [
    {
        "upstream_name": "porting_lib_loot-3.1.0-beta.90+1.21.1.jar",
        "github_repo": "Blockfield/porting-lib",
        "github_tag": "import-2.53.0",
        "sha512": "d0d3199ae1f7144428b09aee66bbcd09b2d9a2781adf02e971dcde517a8adfd82ac43e614feddd6deb8b222aa7aa325a405a0ea692e6596592a2e31badd5420c",
        "out": "files/mods/porting_lib_loot-3.1.0-beta.90+1.21.1-bf1.jar",
        "registry_class": "io/github/fabricators_of_create/porting_lib/loot/PortingLibLoot.class",
    }
]


def github_release_asset(repo, tag, name):
    """Скачать ассет приватного релиза-зеркала (неизменённый апстрим)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit(
            "GITHUB_TOKEN is required to fetch the input jar from the private mirror; "
            "export GITHUB_TOKEN=$(gh auth token)"
        )

    def api(url, accept="application/vnd.github+json"):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Blockfield-CI/1.0",
                "Accept": accept,
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()

    import json

    release = json.loads(
        api(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    )
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return api(asset["url"], accept="application/octet-stream")
    sys.exit(f"{repo}@{tag}: asset {name} not found")


def cached_bytes(path, url, algorithm, expected):
    data = path.read_bytes() if path.is_file() else get_bytes(url)
    actual = hashlib.new(algorithm, data).hexdigest()
    if actual != expected:
        sys.exit(
            f"Checksum mismatch: {path.name} {algorithm} {actual}; expected {expected}"
        )
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return data


def get_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Blockfield-CI/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def sha512(data):
    return hashlib.sha512(data).hexdigest()


def java_tool(command, **kwargs):
    environment = child_env()
    suffix = ".exe" if os.name == "nt" else ""
    home = environment.get("JAVA_HOME")
    candidate = Path(home) / "bin" / (command[0] + suffix) if home else None
    executable = (
        str(candidate)
        if candidate and candidate.is_file()
        else shutil.which(command[0], path=environment["PATH"])
    )
    if executable is None:
        sys.exit("Install JDK 21 and set JAVA_HOME or put its bin directory on PATH")
    version = subprocess.run(
        [executable, "-version"],
        env=environment,
        capture_output=True,
        check=True,
        timeout=30,
    )
    match = re.search(
        rb'\b(?:java|javac|openjdk)(?: version)?\s+"?(\d+)',
        version.stdout + version.stderr,
    )
    if match is None or match[1] != b"21":
        sys.exit(f"JDK 21 required: {executable}")
    return subprocess.run(
        [executable, *command[1:]],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        timeout=120,
        **kwargs,
    )


def compile_transformer():
    tools = ROOT / "files" / "tools"
    jars = []
    for name, checksum in ASM_SHA256.items():
        filename = f"{name}-{ASM_VERSION}.jar"
        path = tools / filename
        cached_bytes(
            path,
            f"https://repo.maven.apache.org/maven2/org/ow2/asm/{name}/{ASM_VERSION}/{filename}",
            "sha256",
            checksum,
        )
        jars.append(str(path))
    classes = tools / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    classpath = os.pathsep.join(jars)
    java_tool(
        [
            "javac",
            "-J-Xmx128m",
            "--release",
            "21",
            "-g:none",
            "-Xlint:all",
            "-Werror",
            "-cp",
            classpath,
            "-d",
            str(classes),
            str(ROOT / "scripts" / "PatchPortingLib.java"),
        ]
    )
    return os.pathsep.join([str(classes), classpath])


def patch_loot_serializers(payload, classpath):
    return java_tool(
        ["java", "-Xmx128m", "-Xverify:all", "-cp", classpath, "PatchPortingLib"],
        input=payload,
    ).stdout


def assert_no_content_id_change(name, upstream_bytes, out_path, removed, changed):
    """Все записи jar'а -- байт-в-байт как в исходнике, кроме удалённых/патченных:
    правка реестра не должна добавлять, удалять или менять игровой контент."""
    source = zipfile.ZipFile(io.BytesIO(upstream_bytes))
    target = zipfile.ZipFile(out_path)
    upstream = {
        entry: source.read(entry)
        for entry in source.namelist()
        if not entry.endswith("/")
    }
    patched = {
        entry: target.read(entry)
        for entry in target.namelist()
        if not entry.endswith("/")
    }
    for entry in upstream:
        if entry in removed:
            continue
        if entry not in patched:
            sys.exit(f"{name}: пропала запись {entry} -- содержимое изменилось?")
    for entry, payload in patched.items():
        if entry not in upstream:
            sys.exit(f"{name}: лишняя запись {entry} -- содержимое изменилось?")
        if entry in changed:
            continue
        if payload != upstream[entry]:
            sys.exit(f"{name}: изменилась запись {entry} -- содержимое изменилось?")


def main():
    if (zlib.ZLIB_VERSION, zlib.ZLIB_RUNTIME_VERSION) != ("1.3.2", "1.3.2"):
        sys.exit(
            f"Expected zlib 1.3.2 (standard), got {zlib.ZLIB_VERSION}/{zlib.ZLIB_RUNTIME_VERSION}"
        )
    for spec in JARS:
        out_path = ROOT / spec["out"]
        local = ROOT / "files" / "mods" / spec["upstream_name"]
        if local.is_file():
            data = local.read_bytes()
        else:
            print(f"скачиваю {spec['upstream_name']}")
            data = github_release_asset(
                spec["github_repo"], spec["github_tag"], spec["upstream_name"]
            )
        actual = sha512(data)
        if actual != spec["sha512"]:
            sys.exit(f"Апстрим изменился: {spec['upstream_name']} sha512 {actual}")
        if spec.get("registry_class"):
            with zipfile.ZipFile(io.BytesIO(data)) as probe:
                if probe.namelist().count(spec["registry_class"]) != 1:
                    sys.exit(
                        f"{spec['registry_class']}: ожидалась ровно одна запись класса"
                    )
            classpath = compile_transformer()
        else:
            classpath = None
        registry_patched = False

        out_path.parent.mkdir(parents=True, exist_ok=True)
        source = zipfile.ZipFile(io.BytesIO(data))
        gone = {
            n
            for n in source.namelist()
            if any(fnmatch.fnmatch(n, pattern) for pattern in spec.get("remove", []))
        }
        removed = []
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                name = info.filename
                if any(
                    fnmatch.fnmatch(name, pattern) for pattern in spec.get("remove", [])
                ):
                    removed.append(name)
                    continue
                payload = source.read(name)
                if name == spec.get("registry_class"):
                    payload = patch_loot_serializers(payload, classpath)
                    registry_patched = True
                target.writestr(info, payload)
        for name in removed:
            print(f"  - {name}")
        if spec.get("registry_class"):
            if not registry_patched:
                sys.exit(f"{spec['registry_class']}: запись класса не встретилась")
            print(f"  ~ {spec['registry_class']}: сериализаторы detached (ASM)")
        assert_no_content_id_change(
            spec["upstream_name"],
            data,
            out_path,
            gone,
            {c for c in (spec.get("registry_class"),) if c},
        )
        print(
            f"{out_path.relative_to(ROOT)} <- {spec['upstream_name']} (sha512 {sha512(out_path.read_bytes())})"
        )


if __name__ == "__main__":
    main()
