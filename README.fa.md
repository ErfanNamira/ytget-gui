<div align="center">

<img src="https://erfannamira.github.io/ytget-gui/assets/img/logo.png" width="110" alt="لوگوی YTGet" />

# YTGet

**دانلودکننده چندسکویی و مدرن یوتیوب — با موتور yt-dlp**

[![Release](https://img.shields.io/github/v/release/ErfanNamira/ytget-gui?style=flat-square&label=release)](https://github.com/ErfanNamira/ytget-gui/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](./LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-blue?style=flat-square)](#-روش-نصب)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-yellow?style=flat-square&logo=python&logoColor=white)](#-راهاندازی-توسعه)
[![PyPI](https://img.shields.io/pypi/v/ytget-gui?style=flat-square&label=pypi)](https://pypi.org/project/ytget-gui/)
[![Downloads](https://img.shields.io/github/downloads/ErfanNamira/ytget-gui/total?style=flat-square&label=downloads)](https://github.com/ErfanNamira/ytget-gui/releases)
[![Stars](https://img.shields.io/github/stars/ErfanNamira/ytget-gui?style=flat-square)](https://github.com/ErfanNamira/ytget-gui/stargazers)

[فارسی] | [English](./README.md)

[وب‌سایت](https://erfannamira.github.io/ytget-gui/) · [انتشارها](https://github.com/ErfanNamira/ytget-gui/releases) · [تاریخچه تغییرات](./CHANGELOG.md)

</div>

---

YTGet یک برنامه رومیزی سبک، ساخته‌شده با **Python** و **PySide6** است که قدرت **yt-dlp** را در رابطی تمیز و کاربرپسند با صف دانلود در اختیارتان می‌گذارد. لینک را بچسبانید، فرمت را انتخاب کنید و شروع کنید — از یک کلیپ تکی تا آرشیو کامل یک کانال، با کنترل کامل روی نام‌گذاری، فاصله‌گذاری درخواست‌ها و خروجی.

- 🖥️ **چندسکویی** — ویندوز، مک‌اواس و لینوکس؛ هر نسخه همه وابستگی‌ها را همراه دارد و بدون نصب اضافی اجرا می‌شود.
- 🎞️ **ویدئو از 480p تا 8K، صدا در MP3/FLAC/Opus** — همراه با تصویر، تگ و متادیتای جاسازی‌شده.
- 🔄 **صف واقعی** — صدها آیتم، پیشرفت زنده و تخمین حجم، ذخیره‌سازی در پس‌زمینه و توقف آنی.
- 🤖 **خودکارسازی داخلی** — پایش کلیپ‌بورد، آیکون سینی، زمان‌بند و اجرا هنگام ورود به سیستم.
- 🛡️ **هم‌گام با یوتیوب** — مدیریت هوشمند player client و Deno برای تغییرات اخیر yt-dlp، به‌همراه پیش‌تنظیم ضد خطای 429.

---

## 🖼 تصاویر

<p align="center">
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-main.jpg" alt="پنجره اصلی YTGet" width="795" />
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-queue.jpg" alt="صف دانلود YTGet" width="795" />
</p>
<p align="center">
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-advanced.jpg" alt="گزینه‌های پیشرفته هر آیتم" width="385" />
  <img src="https://erfannamira.github.io/ytget-gui/assets/img/app-prefs.jpg" alt="تنظیمات" width="385" />
</p>

---

## 🆕 تازه‌های نسخه ۲.۸.۵

- 🔄 **تغییر نوع ضبط آیتم‌های صف، درجا** — چند سطر را انتخاب کنید و با دکمه **TYPE** نوار دسته‌ای (یا راست‌کلیک ← «تغییر نوع ضبط…») به هر پیش‌تنظیمی ببرید. آیتم‌ها جایگاه، جزئیات و تصویر خود را نگه می‌دارند؛ خودِ پنجره هم حدود ۳۰٪ پهن‌تر شده تا چیزی فشرده نباشد.
- 🧩 **رفع خطای «Requested format is not available»** — همه راه‌های شکست اکسترکتور یوتیوب در yt-dlp 2026.10.26+ پوشش داده شده: Deno همراه برنامه فقط وقتی ≥ 2.3.0 باشد استفاده می‌شود، دریافت متادیتا با حذف player client پین‌شده بازیابی می‌شود و لاگ صف دلیل واقعی غیبت فرمت‌ها را نشان می‌دهد. خرابی حل‌کننده چالش EJS در نوامبر ۲۰۲۶ تشخیص داده شده و به‌جای تلاش مجدد بی‌پایان، به‌صورت نیاز به بروزرسانی yt-dlp گزارش می‌شود.
- 📏 **تخمین حجم بر اساس کدک** — کارت‌های صف حجم مربوط به همان کدکی (AV1/VP9/AVC) را نشان می‌دهند که فرمت شما واقعاً ترجیح می‌دهد.
- ⏱️ **فاصله‌گذاری درخواست‌ها: پیش‌تنظیم یا دلخواه** — فاصله‌گذاری توصیه‌شده ضد 429 حالا در «تنظیمات ← پیشرفته ← Request pacing» است، نه در فیلد آرگومان‌های اضافی؛ یا پیش‌تنظیم Sleep را انتخاب کنید یا چهار مقدار خودتان را تنظیم کنید.
- 🛡️ **تاب‌آوری زیرنویس در برابر 429** — اگر دانلود زیرنویس با خطای 429 مواجه شود، زیرنویس فقط برای تلاش‌های مجدد همان آیتم غیرفعال می‌شود و کل دانلود خراب نمی‌شود.
- 📏 عنوان‌های طولانی دیگر چیدمان صف را به‌هم نمی‌ریزند.

تاریخچه کامل در [CHANGELOG.md](./CHANGELOG.md) و [RELEASE_NOTES.md](./RELEASE_NOTES.md).

---

## ☄️ روش نصب

### 🪟 ویندوز

**نصب‌کننده (پیشنهادی)** — فایل `YTGet-<version>-windows-setup.exe` را از
[صفحه انتشارها](https://github.com/ErfanNamira/ytget-gui/releases/latest) دانلود و اجرا کنید.
نصب فقط برای کاربر فعلی است (بدون پیام مدیر سیستم)، با میان‌بر دسکتاپ و گزینه اختیاری «اجرا هنگام ورود».

**نسخه قابل حمل** — [`YTGet-windows.zip`](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-windows.zip) را دانلود کنید (`.7z` هم موجود است)، استخراج کنید و `YTGet.exe` را اجرا کنید.

### 🐧 لینوکس

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg python3-mutagen \
  libxcb-cursor0 libxcb-xinerama0 libxcb-xinput0 libxcb-xfixes0 libxcb-shape0 \
  libxcb-render-util0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
  libxcb-render0 libxcb-shm0 libxcb-sync1 libxcb-util1 libxcb-xkb1
```

سپس [`YTGet-linux.tar.gz`](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-linux.tar.gz) را دانلود و:

```bash
tar -xzf YTGet-linux.tar.gz && chmod +x YTGet && ./YTGet
```

### 🍎 مک‌اواس

نسخه متناسب با دستگاه خود را دانلود کنید —
[Apple Silicon (arm64)](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-macOS-arm64.tar.gz) ·
[Intel (x86_64)](https://github.com/ErfanNamira/ytget-gui/releases/latest/download/YTGet-macOS-x86_64.tar.gz)

<details>
<summary>مراحل راه‌اندازی (اجرای اول)</summary>

```bash
cd Downloads
tar -xzf YTGet-macOS-arm64.tar.gz        # یا YTGet-macOS-x86_64.tar.gz
xattr -d com.apple.quarantine YTGet.app  # حذف قرنطینه
chmod +x YTGet.app/Contents/MacOS/YTGet
mv YTGet.app /Applications/              # اختیاری
open /Applications/YTGet.app
```

</details>

> در مک‌اواس، پس از اولین اجرا یک‌بار **Help → Check yt-dlp Update** را هم اجرا کنید.

### 🐍 PyPI

```bash
pip install ytget-gui            # نصب
pip install --upgrade ytget-gui  # بروزرسانی
```

نسخه PyPI به **FFmpeg** نیاز دارد: یا آن را به `PATH` اضافه کنید، یا فایل‌های `ffmpeg`/`ffprobe` را کنار فایل اجرایی قرار دهید. در مک‌اواس `brew install ffmpeg` و در دبیان/اوبونتو `sudo apt install ffmpeg`.

---

## 🧰 روش استفاده

1. ▶️ اجرای **YTGet** و وارد کردن لینک یوتیوب.
2. 🎚️ انتخاب فرمت — مثلاً 1080p MKV یا MP3.
3. ⚙️ اختیاری: **Advanced** را باز کنید تا برش زمانی یا انتخاب آیتم‌های پلی‌لیست *فقط برای آیتم بعدی* فعال شود (دکمه هنگام فعال بودن نقطه نشان می‌دهد).
4. ➕ کلیک روی **Add to Queue**. همان لینک با فرمت دیگر را می‌خواهید؟ آن فرمت را انتخاب و دوباره اضافه کنید — هر فرمت سطر خودش را دارد.
5. ▶️ کلیک روی **Start Queue**.

برای دانلود بدون دخالت دست، **Tools → Clipboard Watcher** (`Ctrl+Shift+V`) را فعال کنید و فقط لینک‌ها را کپی کنید — ۷۶ سایت شناسایی می‌شود و برای هر دسته (یوتیوب، یوتیوب موزیک، اسپاتیفای و سایر) فرمت پیش‌فرض جداگانه‌ای تعیین می‌شود.

---

## ✨ ویژگی‌ها

| | |
|---|---|
| 🎞️ **ویدئو 480p تا 8K** | MKV / MP4 / WebM با بهترین صدا ادغام‌شده |
| 🎵 **استخراج صدا** | MP3، FLAC و Opus با تصویر، تگ و متادیتا |
| 📂 **پلی‌لیست‌ها** | کامل یا انتخابی، ترتیب معکوس، ردیابی آرشیو |
| 🔁 **چند فرمت از یک لینک** | یک ویدئو هم به‌صورت 1080p و هم MP3 در صف — هر کدام سطر خودش |
| 🔄 **تغییر نوع ضبط درجا** | تغییر آیتم‌های صف به هر پیش‌تنظیم بدون افزودن مجدد |
| 📏 **تخمین حجم** | بر اساس کدک، روی هر کارت صف |
| ✂️ **برش ویدئو** | دانلود بخشی از ویدئو با زمان شروع/پایان، به‌صورت هر آیتم |
| ⏭️ **SponsorBlock** | حذف تبلیغات، اینترو و اوترو |
| 🧩 **فصل‌ها** | جاسازی یا تقسیم بر اساس فصل‌ها |
| 🎼 **متادیتای یوتیوب موزیک** | اطلاعات دقیق موسیقی و آلبوم |
| 📄 **زیرنویس‌ها** | دریافت خودکار، چندزبانه |
| 🌐 **پروکسی** | مسیریابی دانلودها از طریق پروکسی |
| 📅 **فیلتر تاریخ** | فقط ویدئوهای منتشرشده بعد از تاریخ مشخص |
| 🔊 **نرمال‌سازی صدا** | بلندی یکنواخت در همه دانلودها |
| 🧪 **آرگومان‌های سفارشی FFmpeg** | برای کاربران حرفه‌ای |
| 🗃 **سازمان‌دهی کانال‌ها** | مرتب‌سازی خودکار در پوشه آپلودکننده |
| 🖱️ **سینی سیستم** | کنترل صف بدون باز کردن پنجره |
| 📋 **پایش کلیپ‌بورد** | افزودن خودکار هر لینکی که کپی کنید |
| ⏰ **زمان‌بند** | شروع/توقف صف در ساعت مشخص |
| 🚀 **اجرا هنگام ورود** | اجرای برنامه به‌صورت کوچک‌شده در سینی |
| 📄 **ورود/خروج لینک‌ها** | خواندن فهرست لینک از فایل متنی یا ذخیره صف در آن |
| ⏱️ **فاصله‌گذاری درخواست‌ها** | پیش‌تنظیم ضد 429 یا فاصله‌گذاری کاملاً دلخواه در Advanced |
| 🔄 **مدیر بروزرسانی** | بروزرسانی برنامه، yt-dlp و Deno از **Help → Check for Updates** |
| 🩺 **لاگ و گزارش خطا** | `ytget.log` / `crash.log` از **Help → Open Logs Folder** |

---

## 📁 خروجی و نام‌گذاری

- نام‌گذاری تمیز به‌صورت پیش‌فرض: `%(title)s.ext`
- **قوانین نام‌گذاری هر سایت** (تنظیمات ← Output): قالب نام جداگانه برای **یوتیوب**، **یوتیوب موزیک** و **سایر سایت‌ها**، جداگانه برای ویدئو و صدا — مثلاً «هنرمند - شماره قطعه عنوان» برای موسیقی و «آپلودکننده - عنوان» برای ویدئو. همه در ابتدا روی «استفاده از تنظیم عمومی» هستند تا وقتی خودتان چیزی انتخاب کنید چیزی تغییر نکند.
- دانلودهای صوتی شامل تصویر آلبوم (برش‌خورده ۱:۱) و تگ‌های متادیتا هستند.
- اگر دو آپلود متفاوت عنوان یکسانی داشته باشند، هر دو نگه داشته می‌شوند و دومی با نام `Title [video-id].ext` ذخیره می‌شود.
- لاگ‌ها و گزارش‌های خطا در پوشه `logs` پوشه داده برنامه نگهداری می‌شوند.

---

## 🔒 کوکی‌ها (محتوای خصوصی یا محدود به سن)

1. کوکی‌ها را با افزونه [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/lgmpjfekhdgcmpcpnmlhkfkfjdkpmoec) استخراج کنید.
2. فایل را در `_internal/cookies.txt` قرار دهید.

---

## 🩺 رفع اشکال

- **خطای «Requested format is not available»** — مطمئن شوید yt-dlp و Deno بروز هستند (**Help → Check for Updates**، هر کدام یک کلیک). اگر بنر ابتدای برنامه درباره Deno هشدار می‌دهد، یک‌بار آن را بروزرسانی کنید.
- **«n challenge solving failed» یا «Only images are available»** — یک باگ شناخته‌شده در yt-dlp با پلیرهای اواخر نوامبر ۲۰۲۶ یوتیوب است که در **yt-dlp 2026.11.23** رفع شده. yt-dlp را از **Help → Check for Updates** بروزرسانی کنید؛ YTGet این خطا را تشخیص می‌دهد و آیتم را با راهنمای لازم نشانه‌گذاری می‌کند تا بی‌فایده تلاش مجدد نشود. مشکل از Deno، کوکی‌ها یا پروکسی نیست.
- **خطاهای مکرر HTTP 429** — گزینه **Sleep (gentle spacing)** را در «تنظیمات ← پیشرفته ← Request pacing» فعال کنید، یا **Custom** را انتخاب و چهار مقدار دلخواه خود را تنظیم کنید.
- برخی فرمت‌ها خودِ یوتیوب محدود یا موقتاً در دسترس نیستند؛ اگر فرمتی مدام شکست می‌خورد، احتمالاً باید منتظر بروزرسانی yt-dlp بمانید.

---

## 🔧 راه‌اندازی توسعه

**پیش‌نیازها:** [Python 3.13+](https://www.python.org/downloads/) و [FFmpeg](https://www.ffmpeg.org/download.html) در PATH یا پوشه پروژه.

```bash
git clone https://github.com/ErfanNamira/ytget-gui.git
cd ytget-gui
python -m venv venv
source venv/bin/activate        # ویندوز: venv\Scripts\activate
pip install -r requirements.txt

python -m ytget_gui             # اجرای برنامه
python -m pytest                # اجرای تست‌ها
```

---

## 🤝 مشارکت

1. فورک و کلون مخزن
2. ساخت شاخه جدید: `git checkout -b my-feature`
3. کامیت و پوش: `git commit -m "msg" && git push origin my-feature`
4. ارسال Pull Request

---

## 🙏 سپاسگزاری‌ها

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — موتور اصلی دانلود.
- [PySide6 / Qt](https://www.qt.io/qt-for-python) — ابزار رابط کاربری.

---

## 📄 مجوز

این پروژه تحت مجوز **MIT** منتشر شده — جزئیات در فایل [LICENSE](./LICENSE).

---

## 📦 دانلود

👉 [آخرین نسخه](https://github.com/ErfanNamira/ytget-gui/releases/latest)
