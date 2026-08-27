[app]

title = NR17 Visao
package.name = nr17visao
package.domain = br.com.ibero

source.dir = .
source.include_exts = py,java,txt,json,env,png,jpg,jpeg
source.exclude_dirs = .git,.github,__pycache__,bin,.buildozer,venv,.venv

version = 0.1.10

# PDF é gerado pelo Pillow. Não adicionamos ReportLab.
requirements = python3,kivy,pillow

orientation = landscape
fullscreen = 0

android.permissions = CAMERA,INTERNET,WAKE_LOCK

android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

android.add_src = android_src
android.gradle_dependencies = com.google.mlkit:pose-detection:18.0.0-beta5
android.enable_androidx = True
android.add_compile_options = "sourceCompatibility = 1.8", "targetCompatibility = 1.8"

p4a.branch = v2024.01.21

[buildozer]

log_level = 2
warn_on_root = 0
