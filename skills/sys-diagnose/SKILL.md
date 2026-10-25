---
name: sys-diagnose
description: Сбор фактов о системе без изменений — диски, память, журналы, сервисы, сеть, драйверы, устройства. Триггеры «тормозит», «не работает», «место кончилось», «что происходит».
---

# sys-diagnose — диагноз до вмешательства

Пиши от первого лица в женском роде: «проверила», «посмотрела», «нашла».

## Порядок

1. **Симптом словами руководителя** → гипотезы (2–3), а не «сразу лечим».
2. **Собрать факты** под каждую гипотезу (только чтение).
3. **Отсечь** те, что не подтвердились — прямо сказать «не она».
4. **Вердикт** + минимальный следующий шаг.

## Минимальный набор команд (по теме)

| Тема | Что смотрим |
|---|---|
| Место | `df -hT`, `sudo du -xh --max-depth=1 /var \| sort -h`, `du -sh ~/* \| sort -h`, `docker system df`, `sudo journalctl --disk-usage` |
| Память | `free -h`, `ps -eo pid,rss,comm --sort=-rss \| head`, `smem -t` (если есть) |
| Процессор | `uptime`, `top -b -n1 \| head -15`, `systemd-analyze blame` (медленная загрузка) |
| Диски | `lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT`, `sudo smartctl -a /dev/nvme1n1`, `journalctl -k \| grep -i nvme` |
| Сервисы | `systemctl --failed`, `systemctl list-units --state=running`, `journalctl -u <сервис> -n 50` |
| Сеть | `ip -br a`, `resolvectl status`, `ss -tulpn`, `ping -c3 1.1.1.1`, `tracepath` |
| Устройства | `lspci -k`, `lsusb`, `aplay -l`, `xinput list`, `lpstat -p` (принтеры) |
| Графика | `echo $XDG_SESSION_TYPE`, `glxinfo -B`, `journalctl -b \| grep -iE 'amdgpu\|drm\|gnome-shell'` |
| Обновления | `apt list --upgradable`, `snap refresh --list`, `unattended-upgrade --dry-run` |

## Правила

- Никаких изменений на этом шаге, даже «безобидных».
- Команды с `sudo` — **в отдельном блоке** и с пометкой «нужен пароль, выполни сам».
- Если проблема плавающая — сначала включить сбор (журнал), а не гадать.
- Улики сохраняем: вывод — в ответ, значимое — в памятку/журнал, а не «потом вспомню».
