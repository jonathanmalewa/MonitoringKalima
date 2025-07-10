from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import calendar
import os, json

# ====== Konstanta State Form ======
(NAMA, NIP, TUJUAN, PERIODE, PERIODE_START, PERIODE_END, AGENDA, LOKASI, FOTO, KONFIRMASI, STATUS) = range(11)

# ====== Token & Sheet Config ======
TELEGRAM_TOKEN = 'TELEGRAM_TOKEN'
SPREADSHEET_NAME = 'MonitoringDinas'
SHEET_NAME = 'Log'

# ====== Group Telegram Config ======
# Ganti dengan Chat ID group Anda (contoh: -1001234567890)
# Untuk mendapatkan Chat ID: tambahkan bot ke group, lalu kirim pesan dan cek di @userinfobot
GROUP_CHAT_ID = '-1002527924058'  # Ganti dengan Chat ID group Anda

# ====== Setup Google Sheets ======
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_json = json.loads(os.environ['GOOGLE_CREDS_JSON'])
creds = ServiceAccountCredentials.from_json_keyfile_name("creds__json", scope)
client = gspread.authorize(creds)

# Lazy loading untuk sheet - hanya load saat dibutuhkan
def get_sheet():
    try:
        return client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None

# ====== Function to get group chat ID (untuk debugging) ======
async def get_chat_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk mendapatkan Chat ID group - gunakan /getchatid di group"""
    chat = update.effective_chat
    await update.message.reply_text(
        f"Chat ID: `{chat.id}`\n"
        f"Chat Type: {chat.type}\n"
        f"Chat Title: {chat.title}",
        parse_mode='Markdown'
    )

# ====== Function to send notification to group ======
async def send_group_notification(context: ContextTypes.DEFAULT_TYPE, user_data):
    try:
        now = datetime.now()
        gmap = f"https://www.google.com/maps?q={user_data['lat']},{user_data['lon']}"
        
        status_icon = "🚀" if user_data['status'] == 'Check-in' else "🏁"
        notification_text = (
            f"📋 *LAPORAN {user_data['status'].upper()} DINAS*\n\n"
            f"{status_icon} **Status:** {user_data['status']}\n"
            f"📅 **Tanggal:** {now.strftime('%d/%m/%Y %H:%M')}\n"
            f"👤 **Nama:** {user_data['nama']}\n"
            f"🆔 **NIP/NRP:** {user_data['nip']}\n"
            f"📍 **Tujuan:** {user_data['tujuan']}\n"
            f"📅 **Periode:** {user_data['periode']}\n"
            f"📝 **Agenda:** {user_data['agenda']}\n"
            f"🌍 **Lokasi:** [Lihat di Google Maps]({gmap})\n\n"
            "✅ Data telah tercatat dalam sistem monitoring."
        )
        
        # Kirim foto dengan caption laporan ke group
        await context.bot.send_photo(
            chat_id=GROUP_CHAT_ID,
            photo=user_data['foto_file_id'],
            caption=notification_text,
            parse_mode='Markdown'
        )
        
        return True
    except Exception as e:
        print(f"Error sending group notification: {e}")
        print(f"Group Chat ID yang digunakan: {GROUP_CHAT_ID}")
        return False

# ====== Data Sementara per User ======
user_data_dict = {}

# ====== Calendar Helper Functions ======
def create_calendar_keyboard(year, month):
    keyboard = []
    
    # Header dengan nama bulan dan tahun
    month_name = calendar.month_name[month]
    keyboard.append([InlineKeyboardButton(f"{month_name} {year}", callback_data="ignore")])
    
    # Header hari dalam minggu
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in ["S", "M", "T", "W", "T", "F", "S"]])
    
    # Generate kalender
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                callback_data = f"date_{year}_{month}_{day}"
                row.append(InlineKeyboardButton(str(day), callback_data=callback_data))
        keyboard.append(row)
    
    # Navigation buttons
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    keyboard.append([
        InlineKeyboardButton("◀️", callback_data=f"cal_{prev_year}_{prev_month}"),
        InlineKeyboardButton("📅 Hari Ini", callback_data="today"),
        InlineKeyboardButton("▶️", callback_data=f"cal_{next_year}_{next_month}")
    ])
    
    return InlineKeyboardMarkup(keyboard)

# ====== Langkah per Form ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
      keyboard = [
          [InlineKeyboardButton("🚀 Check-in", callback_data='start_checkin')],
          [InlineKeyboardButton("🏁 Check-out", callback_data='start_checkout')],
          [InlineKeyboardButton("🔄 Reset Data", callback_data='reset_data')],
          [InlineKeyboardButton("ℹ️ Info Bot", callback_data='info_bot')]
      ]
      reply_markup = InlineKeyboardMarkup(keyboard)
      
      await update.message.reply_text(
          "🤖 *Bot Monitoring Dinas*\n\n"
          "Selamat datang! Pilih salah satu opsi di bawah ini:",
          parse_mode='Markdown',
          reply_markup=reply_markup
      )
      return STATUS

async def get_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data_dict:
        user_data_dict[user_id] = {}
    
    nama = update.message.text.strip()
    
    # Validasi nama tidak boleh kosong
    if not nama:
        await update.message.reply_text(
            "❌ *Nama tidak boleh kosong!*\n\n"
            "Masukkan *Nama Lengkap* Anda:",
            parse_mode='Markdown'
        )
        return NAMA
    
    # Validasi panjang nama minimal 3 karakter
    if len(nama) < 3:
        await update.message.reply_text(
            "❌ *Nama terlalu pendek!*\n\n"
            "Nama harus minimal 3 karakter.\n\n"
            "Masukkan *Nama Lengkap* Anda:",
            parse_mode='Markdown'
        )
        return NAMA
    
    # Validasi nama hanya boleh mengandung huruf dan spasi
    if not nama.replace(' ', '').isalpha():
        await update.message.reply_text(
            "❌ *Nama hanya boleh mengandung huruf dan spasi!*\n\n"
            "Angka dan karakter khusus tidak diperbolehkan.\n\n"
            "Masukkan *Nama Lengkap* yang benar:",
            parse_mode='Markdown'
        )
        return NAMA
    
    # Validasi nama tidak boleh semua huruf kapital atau semua huruf kecil
    if nama.isupper() or nama.islower():
        await update.message.reply_text(
            "❌ *Format nama tidak sesuai!*\n\n"
            "Nama harus menggunakan format Title Case (huruf pertama kapital).\n\n"
            "Contoh: *Budi Santoso*\n\n"
            "Masukkan *Nama Lengkap* dengan format yang benar:",
            parse_mode='Markdown'
        )
        return NAMA
    
    user_data_dict[user_id]['nama'] = nama
    await update.message.reply_text("✅ Nama valid!\n\nMasukkan *NIP/NRP* Anda:", parse_mode='Markdown')
    return NIP

async def get_nip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nip = update.message.text.strip()
    
    # Validasi NIP tidak boleh kosong
    if not nip:
        await update.message.reply_text(
            "❌ *NIP/NRP tidak boleh kosong!*\n\n"
            "Masukkan *NIP/NRP* yang valid:",
            parse_mode='Markdown'
        )
        return NIP
    
    # Validasi panjang NIP (biasanya 18 digit untuk PNS)
    if len(nip) < 8 or len(nip) > 20:
        await update.message.reply_text(
            "❌ *Format NIP/NRP tidak valid!*\n\n"
            "NIP/NRP harus memiliki 8-20 karakter.\n\n"
            "Masukkan *NIP/NRP* yang benar:",
            parse_mode='Markdown'
        )
        return NIP
    
    # Validasi NIP hanya boleh mengandung angka dan huruf
    if not nip.replace(' ', '').isalnum():
        await update.message.reply_text(
            "❌ *NIP/NRP hanya boleh mengandung angka dan huruf!*\n\n"
            "Karakter khusus tidak diperbolehkan.\n\n"
            "Masukkan *NIP/NRP* yang benar:",
            parse_mode='Markdown'
        )
        return NIP
    
    user_data_dict[update.effective_user.id]['nip'] = nip
    await update.message.reply_text("✅ NIP/NRP valid!\n\nMasukkan *Lokasi Tujuan Dinas*:", parse_mode='Markdown')
    return TUJUAN

async def get_tujuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
      user_data_dict[update.effective_user.id]['tujuan'] = update.message.text
      
      now = datetime.now()
      calendar_keyboard = create_calendar_keyboard(now.year, now.month)
      
      await update.message.reply_text(
          "📅 *Pilih Tanggal Mulai Perjalanan Dinas:*",
          parse_mode='Markdown',
          reply_markup=calendar_keyboard
      )
      return PERIODE_START

async def handle_calendar_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("date_"):
        # Parse tanggal yang dipilih
        _, year, month, day = data.split("_")
        selected_date = datetime(int(year), int(month), int(day))
        date_str = selected_date.strftime("%d/%m/%Y")
        
        if user_id not in user_data_dict:
            user_data_dict[user_id] = {}
        
        # Cek apakah ini untuk tanggal mulai atau selesai
        if 'periode_start' not in user_data_dict[user_id]:
            # Set tanggal mulai
            user_data_dict[user_id]['periode_start'] = selected_date
            
            # Tampilkan kalender untuk tanggal selesai
            calendar_keyboard = create_calendar_keyboard(selected_date.year, selected_date.month)
            await query.edit_message_text(
                f"✅ Tanggal mulai: *{date_str}*\n\n📅 *Pilih Tanggal Selesai Perjalanan Dinas:*",
                parse_mode='Markdown',
                reply_markup=calendar_keyboard
            )
            return PERIODE_END
        else:
            # Set tanggal selesai
            start_date = user_data_dict[user_id]['periode_start']
            
            # Validasi tanggal selesai tidak boleh sebelum tanggal mulai
            if selected_date < start_date:
                await query.edit_message_text(
                    f"❌ *Tanggal selesai tidak boleh sebelum tanggal mulai!*\n\n"
                    f"Tanggal mulai: {start_date.strftime('%d/%m/%Y')}\n\n"
                    f"📅 *Pilih tanggal selesai yang benar:*",
                    parse_mode='Markdown',
                    reply_markup=create_calendar_keyboard(selected_date.year, selected_date.month)
                )
                return PERIODE_END
            
            # Hitung durasi
            durasi = (selected_date - start_date).days + 1
            periode_text = f"{start_date.strftime('%d/%m/%Y')} - {date_str} ({durasi} hari)"
            
            user_data_dict[user_id]['periode'] = periode_text
            
            await query.edit_message_text(
                f"✅ *Periode Perjalanan Dinas:*\n{periode_text}\n\n"
                f"Sekarang, apa *Agenda Hari Ini*?",
                parse_mode='Markdown'
            )
            return AGENDA
    
    elif data.startswith("cal_"):
        # Navigation kalender
        _, year, month = data.split("_")
        calendar_keyboard = create_calendar_keyboard(int(year), int(month))
        
        current_state = "mulai" if 'periode_start' not in user_data_dict.get(user_id, {}) else "selesai"
        text = f"📅 *Pilih Tanggal {current_state.title()} Perjalanan Dinas:*"
        
        if current_state == "selesai":
            start_date = user_data_dict[user_id]['periode_start']
            text = f"✅ Tanggal mulai: *{start_date.strftime('%d/%m/%Y')}*\n\n📅 *Pilih Tanggal Selesai Perjalanan Dinas:*"
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=calendar_keyboard)
        return PERIODE_END if current_state == "selesai" else PERIODE_START
    
    elif data == "today":
        # Pilih hari ini
        today = datetime.now()
        date_str = today.strftime("%d/%m/%Y")
        
        if user_id not in user_data_dict:
            user_data_dict[user_id] = {}
        
        if 'periode_start' not in user_data_dict[user_id]:
            user_data_dict[user_id]['periode_start'] = today
            calendar_keyboard = create_calendar_keyboard(today.year, today.month)
            await query.edit_message_text(
                f"✅ Tanggal mulai: *{date_str}*\n\n📅 *Pilih Tanggal Selesai Perjalanan Dinas:*",
                parse_mode='Markdown',
                reply_markup=calendar_keyboard
            )
            return PERIODE_END
        else:
            start_date = user_data_dict[user_id]['periode_start']
            durasi = (today - start_date).days + 1
            periode_text = f"{start_date.strftime('%d/%m/%Y')} - {date_str} ({durasi} hari)"
            
            user_data_dict[user_id]['periode'] = periode_text
            
            await query.edit_message_text(
                f"✅ *Periode Perjalanan Dinas:*\n{periode_text}\n\n"
                f"Sekarang, apa *Agenda Hari Ini*?",
                parse_mode='Markdown'
            )
            return AGENDA
    
    return PERIODE_START

async def get_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
      user_data_dict[update.effective_user.id]['agenda'] = update.message.text
      await update.message.reply_text(
          "📍 Silakan *kirim lokasi real-time* Anda.\n\n"
          "⚠️ *PENTING:* Gunakan tombol 📎 (attachment) → Location untuk mengirim lokasi real-time.\n"
          "❌ Mengetik alamat tidak akan diterima!",
          parse_mode='Markdown'
      )
      return LOKASI

async def reject_file_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
      await update.message.reply_text(
          "❌ *Foto dari galeri/file tidak diterima!*\n\n"
          "📸 Silakan ambil foto langsung menggunakan kamera.\n\n"
          "💡 *Cara mengambil foto yang benar:*\n"
          "1. Tekan tombol 📎 (attachment)\n"
          "2. Pilih 'Camera' (bukan 'Photo & Video')\n"
          "3. Ambil foto langsung dari kamera\n"
          "4. Kirim foto tersebut\n\n"
          "⚠️ Foto harus fresh dari kamera untuk memastikan keaslian lokasi dan waktu!",
          parse_mode='Markdown'
      )
      return FOTO

async def reject_text_in_photo_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
      await update.message.reply_text(
          "❌ *Hanya foto yang diterima!*\n\n"
          "📸 Silakan kirim foto kegiatan hari ini.\n\n"
          "💡 *Cara mengambil foto:*\n"
          "1. Tekan tombol 📎 (attachment)\n"
          "2. Pilih 'Camera'\n"
          "3. Ambil foto langsung dari kamera\n"
          "4. Kirim foto tersebut",
          parse_mode='Markdown'
      )
      return FOTO

async def get_lokasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lokasi = update.message.location
    
    # Validasi koordinat tidak boleh 0,0 (fake location)
    if lokasi.latitude == 0.0 and lokasi.longitude == 0.0:
        await update.message.reply_text(
            "❌ *Lokasi tidak valid!*\n\n"
            "Koordinat 0,0 terdeteksi sebagai lokasi palsu.\n\n"
            "📍 Silakan kirim lokasi real-time yang valid:",
            parse_mode='Markdown'
        )
        return LOKASI
    
    # Validasi koordinat tidak boleh sama persis dengan koordinat terkenal (fake/spoofing)
    # Koordinat Jakarta: -6.2088, 106.8456
    # Koordinat Bandung: -6.9175, 107.6191
    known_fake_coords = [
        (0.0, 0.0),
        (-6.2088, 106.8456),  # Jakarta (koordinat umum)
        (-6.9175, 107.6191),  # Bandung (koordinat umum)
        (37.7749, -122.4194), # San Francisco
        (40.7128, -74.0060),  # New York
        (51.5074, -0.1278),   # London
    ]
    
    for fake_lat, fake_lon in known_fake_coords:
        if abs(lokasi.latitude - fake_lat) < 0.0001 and abs(lokasi.longitude - fake_lon) < 0.0001:
            await update.message.reply_text(
                "❌ *Lokasi terdeteksi sebagai koordinat palsu!*\n\n"
                "Sistem mendeteksi Anda menggunakan koordinat yang umum digunakan untuk spoofing.\n\n"
                "📍 Silakan kirim lokasi real-time Anda yang sebenarnya:",
                parse_mode='Markdown'
            )
            return LOKASI
    
    # Validasi rentang koordinat Indonesia
    # Indonesia: Latitude -11 to 6, Longitude 95 to 141
    if not (-11 <= lokasi.latitude <= 6 and 95 <= lokasi.longitude <= 141):
        await update.message.reply_text(
            "❌ *Lokasi di luar wilayah Indonesia!*\n\n"
            "Sistem mendeteksi lokasi Anda berada di luar wilayah Indonesia.\n\n"
            "📍 Pastikan GPS aktif dan kirim lokasi real-time yang valid:",
            parse_mode='Markdown'
        )
        return LOKASI
    
    # Validasi presisi koordinat (koordinat real biasanya memiliki banyak desimal)
    lat_decimals = len(str(lokasi.latitude).split('.')[-1])
    lon_decimals = len(str(lokasi.longitude).split('.')[-1])
    
    if lat_decimals < 4 or lon_decimals < 4:
        await update.message.reply_text(
            "❌ *Lokasi kurang presisi!*\n\n"
            "Koordinat yang dikirim terlalu bulat, kemungkinan lokasi palsu.\n\n"
            "📍 Pastikan GPS aktif dan kirim lokasi real-time dengan presisi tinggi:",
            parse_mode='Markdown'
        )
        return LOKASI
    
    # Simpan lokasi dengan timestamp untuk tracking
    user_data_dict[update.effective_user.id]['lat'] = lokasi.latitude
    user_data_dict[update.effective_user.id]['lon'] = lokasi.longitude
    user_data_dict[update.effective_user.id]['location_timestamp'] = datetime.now().isoformat()
    
    await update.message.reply_text(
        "✅ *Lokasi real-time diterima!*\n\n"
        f"📍 Koordinat: {lokasi.latitude:.6f}, {lokasi.longitude:.6f}\n\n"
        "📸 Sekarang, silakan kirim *foto kegiatan hari ini*.",
        parse_mode='Markdown'
    )
    return FOTO

async def reject_text_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
      await update.message.reply_text(
          "❌ *Maaf, input teks tidak diterima!*\n\n"
          "📍 Silakan gunakan tombol 📎 (attachment) → Location untuk mengirim lokasi real-time Anda.\n\n"
          "💡 *Cara mengirim lokasi:*\n"
          "1. Tekan tombol 📎 (attachment)\n"
          "2. Pilih 'Location'\n"
          "3. Pilih 'Send My Current Location'\n"
          "4. Izinkan akses lokasi jika diminta",
          parse_mode='Markdown'
      )
      return LOKASI

async def get_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Validasi foto harus dari kamera (bukan file)
        photo = update.message.photo[-1]
        
        # Cek apakah foto dikirim sebagai file (dari galeri) atau langsung dari kamera
        if update.message.document:
            await update.message.reply_text(
                "❌ *Foto harus langsung dari kamera!*\n\n"
                "📸 Silakan gunakan kamera untuk mengambil foto baru, jangan kirim dari galeri.\n\n"
                "💡 *Cara mengambil foto:*\n"
                "1. Tekan tombol 📎 (attachment)\n"
                "2. Pilih 'Camera'\n"
                "3. Ambil foto langsung dari kamera\n"
                "4. Kirim foto tersebut",
                parse_mode='Markdown'
            )
            return FOTO
        
        # Validasi ketat untuk memastikan foto dari kamera
        file_size = photo.file_size
        width = photo.width
        height = photo.height
        
        # Validasi 1: Ukuran file minimal (disesuaikan untuk iPhone/Android modern)
        if file_size and file_size < 30000:  # Kurang dari 30KB (sangat kecil untuk foto kamera)
            await update.message.reply_text(
                "❌ *Foto terlalu kecil - kemungkinan bukan dari kamera!*\n\n"
                "📸 Foto dari kamera iPhone/Android biasanya > 30KB.\n\n"
                "💡 *Pastikan:*\n"
                "• Ambil foto LANGSUNG dari kamera\n"
                "• Tekan tombol 📎 → Camera (bukan Photo & Video)\n"
                "• Jangan gunakan mode hemat data\n\n"
                "🔄 Coba lagi dengan foto fresh dari kamera:",
                parse_mode='Markdown'
            )
            return FOTO
        
        # Validasi 2: Rasio aspek foto (foto kamera modern biasanya 4:3 atau 16:9)
        if width and height:
            aspect_ratio = width / height
            # Foto kamera biasanya memiliki rasio 0.75 (4:3) atau 1.78 (16:9) atau 1.33 (3:4)
            valid_ratios = [0.75, 1.33, 1.78, 0.56]  # 4:3, 3:4, 16:9, 9:16
            
            is_valid_ratio = any(abs(aspect_ratio - ratio) < 0.1 for ratio in valid_ratios)
            
            if not is_valid_ratio:
                await update.message.reply_text(
                    "❌ *Rasio foto tidak sesuai format kamera!*\n\n"
                    f"📏 Rasio foto: {aspect_ratio:.2f}\n\n"
                    "📸 Silakan ambil foto dengan format standar kamera:\n"
                    "• 4:3 (landscape)\n"
                    "• 3:4 (portrait)\n"
                    "• 16:9 (wide)\n\n"
                    "🔄 Ambil foto baru langsung dari kamera:",
                    parse_mode='Markdown'
                )
                return FOTO
        
        # Validasi 3: Cek timestamp foto dengan timestamp lokasi
        current_time = datetime.now()
        if 'location_timestamp' in user_data_dict[update.effective_user.id]:
            location_time = datetime.fromisoformat(user_data_dict[update.effective_user.id]['location_timestamp'])
            time_diff = (current_time - location_time).total_seconds()
            
            # Foto harus diambil dalam 5 menit setelah lokasi dikirim
            if time_diff > 300:  # 5 menit
                await update.message.reply_text(
                    "❌ *Foto terlalu lama setelah lokasi dikirim!*\n\n"
                    "⏱️ Foto harus diambil dalam 5 menit setelah lokasi dikirim.\n\n"
                    "📸 Silakan ambil foto baru langsung dari kamera:",
                    parse_mode='Markdown'
                )
                return FOTO
        
        # Validasi 4: Minimum resolusi untuk foto kamera (disesuaikan untuk iPhone/Android)
        if width and height:
            min_resolution = 240  # Minimal 240p (lebih fleksibel untuk foto Telegram)
            if width < min_resolution or height < min_resolution:
                await update.message.reply_text(
                    "❌ *Resolusi foto terlalu rendah!*\n\n"
                    f"📐 Resolusi: {width}x{height}\n"
                    f"📏 Minimal: {min_resolution}p\n\n"
                    "📸 Silakan ambil foto dengan resolusi yang lebih tinggi:\n"
                    "• Pastikan kamera dalam mode resolusi normal\n"
                    "• Jangan gunakan mode hemat data\n\n"
                    "🔄 Ambil foto baru dengan resolusi tinggi:",
                    parse_mode='Markdown'
                )
                return FOTO
        
        # Validasi 5: Deteksi foto screenshot atau hasil edit (disesuaikan untuk iPhone/Android)
        # iPhone HEIC→JPEG compression menghasilkan rasio yang berbeda
        if file_size and width and height:
            # Hitung rasio file size per pixel
            pixels = width * height
            bytes_per_pixel = file_size / pixels
            
            # Foto kamera iPhone/Android: 0.1-5 bytes per pixel (lebih fleksibel karena kompresi HEIC→JPEG)
            # Foto screenshot/edit: biasanya > 8 bytes per pixel atau < 0.05 bytes per pixel
            if bytes_per_pixel > 8.0 or bytes_per_pixel < 0.05:
                await update.message.reply_text(
                    "❌ *Foto terdeteksi sebagai screenshot atau hasil edit!*\n\n"
                    f"📊 Rasio file/pixel: {bytes_per_pixel:.3f} (tidak normal untuk foto kamera)\n\n"
                    "📸 Silakan ambil foto LANGSUNG dari kamera:\n"
                    "• Jangan screenshot foto lain\n"
                    "• Jangan edit atau filter foto\n"
                    "• Ambil foto original dari kamera iPhone\n\n"
                    "🔄 Coba lagi dengan foto fresh dari kamera:",
                    parse_mode='Markdown'
                )
                return FOTO
        
        # Simpan file foto dan file_id untuk pengiriman ulang
        file = await photo.get_file()
        user_data_dict[update.effective_user.id]['foto_file_id'] = photo.file_id
        user_data_dict[update.effective_user.id]['foto'] = file.file_path
        user_data_dict[update.effective_user.id]['foto_timestamp'] = current_time.isoformat()
        user_data_dict[update.effective_user.id]['foto_size'] = file_size
        user_data_dict[update.effective_user.id]['foto_resolution'] = f"{width}x{height}"

        # Tampilkan konfirmasi data dengan foto
        data = user_data_dict[update.effective_user.id]
        gmap = f"https://www.google.com/maps?q={data['lat']},{data['lon']}"
        
        status_icon = "🚀" if data['status'] == 'Check-in' else "🏁"
        konfirmasi_text = (
            f"📋 *KONFIRMASI DATA {data['status'].upper()}*\n\n"
            f"{status_icon} **Status:** {data['status']}\n"
            f"👤 **Nama:** {data['nama']}\n"
            f"🆔 **NIP/NRP:** {data['nip']}\n"
            f"📍 **Tujuan:** {data['tujuan']}\n"
            f"📅 **Periode:** {data['periode']}\n"
            f"📝 **Agenda:** {data['agenda']}\n"
            f"🌍 **Lokasi:** [Lihat di Maps]({gmap})\n\n"
            f"📸 **Foto kegiatan** ✅ *Terverifikasi dari kamera*"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Konfirmasi & Simpan", callback_data='konfirmasi_simpan')],
            [InlineKeyboardButton("🔄 Reset & Mulai Ulang", callback_data='konfirmasi_reset')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Kirim foto dengan caption konfirmasi
        await update.message.reply_photo(
            photo=photo.file_id,
            caption=konfirmasi_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return KONFIRMASI
        
    except Exception as e:
        await update.message.reply_text("❌ Terjadi kesalahan saat memproses foto. Silakan coba lagi.")
        print(f"Error: {e}")
        return FOTO

async def handle_konfirmasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'konfirmasi_simpan':
        try:
            # Simpan ke Sheets dengan lazy loading
            data = user_data_dict[update.effective_user.id]
            now = datetime.now()
            gmap = f"https://www.google.com/maps?q={data['lat']},{data['lon']}"

            sheet = get_sheet()
            if sheet:
                sheet.append_row([
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    data['nama'],
                    data['nip'],
                    data['tujuan'],
                    data['periode'],
                    data['agenda'],
                    data['lat'],
                    data['lon'],
                    gmap,
                    data['foto'],
                    data['status']
                ])
                
                # Kirim notifikasi ke group
                group_sent = await send_group_notification(context, data)
                
                keyboard = [
                    [InlineKeyboardButton("🚀 Check-in Lagi", callback_data='start_checkin')],
                    [InlineKeyboardButton("🏁 Check-out Lagi", callback_data='start_checkout')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                status_text = data['status'].lower()
                success_message = (
                    "✅ *DATA BERHASIL DISIMPAN!*\n\n"
                    f"{data['status']} harian Anda telah tercatat dengan sukses."
                )
                
                if group_sent:
                    success_message += "\n📢 Notifikasi telah dikirim ke group!"
                else:
                    success_message += "\n⚠️ Data tersimpan, tapi gagal kirim ke group."
                
                success_message += "\n\nTerima kasih!"
                
                # Hapus pesan lama dan kirim pesan baru (karena pesan sebelumnya adalah foto)
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text=success_message,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                keyboard = [[InlineKeyboardButton("🔄 Coba Lagi", callback_data='start_checkin')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Hapus pesan lama dan kirim pesan baru
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text="❌ Tidak dapat terhubung ke database. Data tidak tersimpan.",
                    reply_markup=reply_markup
                )
            
            user_data_dict.pop(update.effective_user.id)
            return ConversationHandler.END
            
        except Exception as e:
            try:
                # Hapus pesan lama dan kirim pesan baru
                await query.message.delete()
                keyboard = [[InlineKeyboardButton("🔄 Coba Lagi", callback_data='start_checkin')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text="❌ Terjadi kesalahan saat menyimpan data. Silakan coba lagi.",
                    reply_markup=reply_markup
                )
            except:
                # Jika gagal hapus pesan, kirim pesan baru saja
                await query.message.reply_text("❌ Terjadi kesalahan saat menyimpan data. Silakan coba lagi.")
            print(f"Error: {e}")
            return ConversationHandler.END
    
    elif query.data == 'konfirmasi_reset':
        user_id = query.from_user.id
        if user_id in user_data_dict:
            user_data_dict.pop(user_id)
        
        keyboard = [[InlineKeyboardButton("🚀 Mulai Check-in Baru", callback_data='start_checkin')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Hapus pesan lama dan kirim pesan baru
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="🔄 *DATA TELAH DIRESET!*\n\nSemua data telah dihapus. Silakan mulai check-in dari awal:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'start_checkin':
        user_data_dict[query.from_user.id] = {'status': 'Check-in'}
        await query.edit_message_text(
            "🚀 Mari mulai check-in harian Anda!\n\nMasukkan *Nama Lengkap* Anda:",
            parse_mode='Markdown'
        )
        return NAMA
    
    elif query.data == 'start_checkout':
        user_data_dict[query.from_user.id] = {'status': 'Check-out'}
        await query.edit_message_text(
            "🏁 Mari mulai check-out harian Anda!\n\nMasukkan *Nama Lengkap* Anda:",
            parse_mode='Markdown'
        )
        return NAMA
    
    elif query.data == 'reset_data':
        user_id = query.from_user.id
        if user_id in user_data_dict:
            user_data_dict.pop(user_id)
        
        keyboard = [
            [InlineKeyboardButton("🚀 Check-in Baru", callback_data='start_checkin')],
            [InlineKeyboardButton("🏁 Check-out Baru", callback_data='start_checkout')],
            [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ Data Anda telah direset!\n\nSilakan mulai check-in baru:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    elif query.data == 'info_bot':
        keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ℹ️ *Informasi Bot*\n\n"
            "Bot ini digunakan untuk monitoring check-in harian pegawai.\n\n"
            "*Fitur:*\n"
            "• Input nama dan NIP\n"
            "• Lokasi tujuan dinas\n"
            "• Periode perjalanan dinas\n"
            "• Agenda kegiatan\n"
            "• Lokasi real-time\n"
            "• Upload foto kegiatan\n"
            "• Konfirmasi data sebelum disimpan\n"
            "• Otomatis tersimpan ke Google Sheets\n\n"
            "*Perintah:*\n"
            "/start - Mulai/restart bot\n"
            "/cancel - Batalkan proses",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    elif query.data == 'back_to_menu':
        keyboard = [
            [InlineKeyboardButton("🚀 Check-in", callback_data='start_checkin')],
            [InlineKeyboardButton("🏁 Check-out", callback_data='start_checkout')],
            [InlineKeyboardButton("🔄 Reset Data", callback_data='reset_data')],
            [InlineKeyboardButton("ℹ️ Info Bot", callback_data='info_bot')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🤖 *Bot Monitoring Dinas*\n\n"
            "Selamat datang! Pilih salah satu opsi di bawah ini:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
      user_id = update.effective_user.id
      if user_id in user_data_dict:
          user_data_dict.pop(user_id)
      
      keyboard = [[InlineKeyboardButton("🚀 Mulai Lagi", callback_data='start_checkin')]]
      reply_markup = InlineKeyboardMarkup(keyboard)
      
      await update.message.reply_text(
          "❌ Formulir dibatalkan. Data telah direset.",
          reply_markup=reply_markup
      )
      return ConversationHandler.END

  # ====== Main Bot Setup ======
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data_dict:
        user_data_dict.pop(user_id)
    
    keyboard = [[InlineKeyboardButton("🚀 Mulai Check-in Baru", callback_data='start_checkin')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔄 Data Anda telah direset!\n\nSilakan mulai check-in baru:",
        reply_markup=reply_markup
    )

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CallbackQueryHandler(button_callback, pattern='^start_checkin$|^start_checkout$')],
        states={
            STATUS: [CallbackQueryHandler(button_callback)],
            NAMA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_nama),
                CallbackQueryHandler(button_callback)
            ],
            NIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nip)],
            TUJUAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tujuan)],
            PERIODE_START: [CallbackQueryHandler(handle_calendar_selection)],
            PERIODE_END: [CallbackQueryHandler(handle_calendar_selection)],
            AGENDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_agenda)],
            LOKASI: [
                MessageHandler(filters.LOCATION, get_lokasi),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reject_text_location)
            ],
            FOTO: [
                MessageHandler(filters.PHOTO, get_foto),
                MessageHandler(filters.Document.IMAGE, reject_file_photo),
                MessageHandler(filters.Document.ALL, reject_file_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reject_text_in_photo_state)
            ],
            KONFIRMASI: [CallbackQueryHandler(handle_konfirmasi)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('reset', reset_command))
    application.add_handler(CommandHandler('getchatid', get_chat_info))  # Untuk mendapatkan Chat ID
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot started successfully!")
    application.run_polling()

if __name__ == "__main__":
    main()
