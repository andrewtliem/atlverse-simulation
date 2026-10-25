"use strict";
// Learning aids for students: glossary/help (Bahasa Indonesia, Arena terms kept in English),
// a plain-language reading of the results, charts in the Summary, and a guided first model.
// Loaded after the editor script, whose globals (model, lastResults, eachNode, ...) it uses.

// ======================= glossary =======================
// [id, term, category, aliases (labels/column headers that link here), explanation (HTML)]
const GLOSS = [
  // ---- konsep dasar
  ["entity", "Entity", "Konsep dasar", ["Entity", "Entity Type"],
   `Objek yang <b>bergerak melewati</b> sistem: pelanggan, pasien, pesanan, part. Entity dibuat oleh <i>Create</i>, menunggu dan dilayani di <i>Process</i>, lalu keluar di <i>Dispose</i>.
    <br><b>Entity Type</b> mengelompokkan entity (mis. "Pasien", "Job") supaya statistiknya dilaporkan terpisah dan gambarnya di animasi bisa berbeda.`],
  ["attribute", "Attribute", "Konsep dasar", ["Attribute", "Attribute Name"],
   `Nilai yang <b>melekat pada setiap entity</b>, ikut terbawa ke mana pun entity pergi. Contoh: waktu kedatangan, tingkat kegawatan pasien, jenis produk.
    Setiap entity punya nilainya sendiri. Bandingkan dengan <a data-term="variable">Variable</a> yang hanya satu untuk seluruh model.`],
  ["variable", "Variable", "Konsep dasar", ["Variable"],
   `Nilai <b>global</b>: satu untuk seluruh model dan bisa dibaca atau diubah oleh entity mana pun. Contoh: jumlah total produk cacat, status mesin, parameter yang ingin dicoba-coba.`],
  ["resource", "Resource", "Konsep dasar", ["Resource", "Resource Name"],
   `Sesuatu yang <b>terbatas jumlahnya</b> dan dibutuhkan entity untuk dilayani: teller, dokter, mesin. Entity harus <i>Seize</i> (merebut) resource. Kalau semua unit sedang dipakai, entity <b>antre</b>.
    Setelah selesai, entity <i>Release</i> resource supaya bisa dipakai entity lain.`],
  ["capacity", "Capacity", "Konsep dasar", ["Capacity", "Capacity ↔ Resource", "Quantity"],
   `Jumlah unit resource yang tersedia, misalnya 2 teller. <i>Fixed Capacity</i> berarti jumlahnya tetap. <i>Based on Schedule</i> berarti jumlahnya mengikuti jadwal, misalnya 3 dokter siang dan 1 dokter malam.
    Capacity diatur di data module <b>Resource</b>; di module Process/Seize ditampilkan juga sebagai <b>Capacity ↔ Resource</b> (nilai yang sama, ubah di salah satu tempat).
    Jangan tertukar dengan <b>Quantity</b> di module: Quantity = berapa unit yang dipakai <i>setiap entity</i>. Menambah teller berarti menaikkan Capacity, bukan Quantity. Capacity 2 dengan Quantity 2 sama saja dengan 1 teller: setiap nasabah memakai dua teller sekaligus.`],
  ["queue", "Queue", "Konsep dasar", ["Queue", "Queue Name"],
   `Tempat entity <b>menunggu</b> ketika resource yang dibutuhkan sedang penuh. Setiap Process yang melakukan Seize otomatis punya antrean bernama "<i>Nama Process</i>.Queue".
    Contoh: Process <b>Triage</b> → antrean <code>Triage.Queue</code>, sehingga panjangnya dibaca dengan <code>NQ(Triage.Queue)</code>.
    Semua antrean ini otomatis tercantum di data module Queue. Urutan pelayanan defaultnya <i>First In First Out</i>; di sana bisa diubah, misalnya berdasarkan atribut prioritas (Highest Attribute Value).`],
  ["schedule", "Schedule", "Konsep dasar", ["Schedule", "Schedule Name"],
   `Pola yang berubah terhadap waktu: <b>kapasitas</b> resource per jam (shift kerja) atau <b>laju kedatangan</b> per jam (jam sibuk). Bisa diatur secara grafis lewat Schedule → <i>Edit graphically</i>.`],
  ["set", "Set", "Konsep dasar", ["Set", "Set Name"],
   `Kumpulan elemen sejenis, misalnya beberapa resource. Process bisa Seize "salah satu anggota set" dengan aturan pemilihan tertentu, misalnya <i>Cyclical</i> atau <i>Smallest Number Busy</i>.`],
  ["expression", "Expression", "Konsep dasar", ["Expression", "Expression Value"],
   `Rumus yang dihitung saat simulasi berjalan. Isinya bisa angka, distribusi acak (EXPO(5)), atribut, variable, dan fungsi sistem (TNOW, NQ, NR, …).
    Contoh: <code>TRIA(3, 4, 6)</code>, <code>NQ(Teller.Queue) &gt; 5</code>, <code>TNOW - ArrTime</code>.`],
  ["base_units", "Base Time Units", "Konsep dasar", ["Base Time Units", "Time units"],
   `Satuan waktu yang dipakai di laporan. Semua waktu di modul, misalnya "5 Minutes" atau "2 Hours", diubah ke satuan ini. Kalau base unit-nya menit, angka 97.9 di laporan berarti 97.9 menit.`],
  ["tnow", "Simulation clock (TNOW)", "Konsep dasar", ["TNOW", "Simulation clock"],
   `Jam simulasi. Waktu tidak berjalan per detik seperti jam dinding, tetapi <b>melompat dari kejadian ke kejadian</b>: kedatangan, selesai dilayani, perubahan jadwal. Inilah yang disebut <i>discrete-event simulation</i>.`],
  ["random", "Keacakan & distribusi", "Konsep dasar", ["Distribution"],
   `Waktu antar kedatangan dan waktu pelayanan di dunia nyata bervariasi, jadi dimodelkan dengan <b>distribusi peluang</b>. Akibatnya setiap run memberi hasil yang sedikit berbeda.
    Karena itu kita menjalankan beberapa <a data-term="replication">replikasi</a> dan melaporkan <a data-term="half_width">half width</a>.`],

  // ---- modul
  ["mod_create", "Create", "Modul", [],
   `Titik <b>awal</b> entity masuk ke sistem.
    <ul>
      <li><i>Type</i>: <b>Random (Expo)</b> berarti waktu antar kedatangan acak eksponensial dengan rata-rata <i>Value</i>, cocok untuk kedatangan pelanggan yang saling bebas. <b>Constant</b> berarti selalu sama. <b>Schedule</b> berarti laju mengikuti jadwal.</li>
      <li><i>Entities per Arrival</i>: berapa entity yang datang sekaligus.</li>
      <li><i>Max Arrivals</i>: batas jumlah kedatangan.</li>
      <li><i>First Creation</i>: waktu kedatangan pertama.</li>
    </ul>`],
  ["mod_dispose", "Dispose", "Modul", [],
   `Titik <b>akhir</b>: entity keluar dari sistem. Kalau <i>Record Entity Statistics</i> dicentang, waktu total entity di sistem dicatat ke laporan Entity.`],
  ["mod_process", "Process", "Modul", ["Action"],
   `Tempat entity <b>dilayani</b>. <i>Action</i> menentukan apa yang terjadi:
    <ul><li><b>Delay</b>: hanya menunggu selama waktu tertentu, tanpa resource.</li>
    <li><b>Seize Delay Release</b>: ambil resource (antre kalau penuh), dilayani, lalu lepaskan resource. Ini yang paling umum.</li>
    <li><b>Seize Delay</b>: resource tidak dilepas di sini, tetapi nanti di modul lain (Release atau Process <i>Delay Release</i>).</li>
    <li><b>Delay Release</b>: melepas resource yang diambil sebelumnya.</li></ul>
    <i>Allocation</i> menentukan waktu prosesnya dihitung sebagai jenis waktu apa (lihat <a data-term="va_time">VA Time</a>).`],
  ["mod_decide", "Decide", "Modul", ["Percent True"],
   `<b>Percabangan</b>. <i>2-way by Chance</i>: misalnya 15% entity ke cabang True. <i>by Condition</i>: berdasarkan kondisi, misalnya <code>Criticality == 1</code>. <i>N-way</i> untuk lebih dari dua cabang.`],
  ["mod_assign", "Assign", "Modul", ["Assignments"],
   `<b>Memberi nilai</b> ke attribute, variable, entity type, gambar entity, atau kapasitas resource. Contoh: <code>ArrTime = TNOW</code> mencatat waktu kedatangan entity.`],
  ["mod_record", "Record", "Modul", [],
   `<b>Mencatat statistik</b> buatan sendiri saat entity lewat. <i>Count</i> menambah counter. <i>Time Interval</i> mencatat TNOW dikurangi atribut, misalnya lama di sistem. <i>Expression</i> mencatat nilai rumus. <i>Time Between</i> mencatat jarak waktu antar entity. Hasilnya muncul di <b>User Specified</b>.`],
  ["mod_batch", "Batch", "Modul", [],
   `Mengumpulkan beberapa entity menjadi <b>satu kelompok</b>, misalnya 10 part menjadi 1 kotak. Entity menunggu sampai jumlahnya cukup. <i>Temporary</i> berarti kelompok bisa dipecah lagi dengan Separate.`],
  ["mod_separate", "Separate", "Modul", [],
   `Memecah batch kembali ke anggota aslinya, atau membuat <b>duplikat</b> entity.`],
  ["mod_seize", "Seize", "Modul", ["Seize"],
   `Mengambil satu atau lebih unit resource. Kalau resource penuh, entity menunggu di antrean modul ini. Entity dengan <a data-term="priority">priority</a> lebih kecil dilayani duluan.`],
  ["mod_delay", "Delay", "Modul", [], `Menahan entity selama waktu tertentu tanpa memakai resource baru.`],
  ["mod_release", "Release", "Modul", [], `Melepas resource yang sebelumnya di-Seize sehingga entity lain di antrean bisa dilayani.`],
  ["mod_hold", "Hold", "Modul", [],
   `Menahan entity di antrean sampai ada <b>sinyal</b> (<i>Wait for Signal</i>), sampai sebuah kondisi terpenuhi (<i>Scan for Condition</i>), atau sampai dilepas modul lain (<i>Infinite Hold</i>).`],
  ["mod_signal", "Signal", "Modul", [], `Mengirim sinyal bernomor yang melepas entity yang sedang menunggu di Hold dengan kode sinyal yang sama.`],
  ["submodel", "Submodel", "Modul", ["Submodel"],
   `Process dengan Type <i>Submodel</i> berisi logika lain di dalamnya. Klik dua kali untuk masuk. Gunanya untuk merapikan model besar menjadi bagian-bagian.`],
  ["priority", "Priority", "Modul", ["Priority"],
   `Urutan pelayanan saat beberapa entity menunggu resource yang sama. <b>Angka lebih kecil dilayani lebih dulu</b>: High (1) lebih dulu dari Low (3). Bisa berupa expression, misalnya atribut kegawatan.`],
  ["allocation", "Allocation", "Modul", ["Allocation"],
   `Jenis waktu atau biaya yang dicatat untuk aktivitas ini: Value Added, Non-Value Added, Transfer, Wait, atau Other. Lihat <a data-term="va_time">VA Time</a>.`],

  // ---- run setup
  ["replication", "Replication", "Run Setup", ["Number of Replications", "Replications", "replication"],
   `Satu kali menjalankan simulasi dari awal sampai akhir dengan bilangan acak yang <b>berbeda</b>. Karena hasil tiap run bervariasi, kita menjalankan beberapa replikasi, lalu melaporkan rata-ratanya dan <a data-term="half_width">half width</a>.
    Untuk tugas, gunakan setidaknya 5–10 replikasi.`],
  ["run_length", "Replication Length", "Run Setup", ["Replication Length"],
   `Berapa lama sistem disimulasikan dalam satu replikasi, misalnya 8 jam (satu hari kerja) atau 1 tahun. Kalau dikosongkan, run berhenti karena <i>Terminating Condition</i> atau karena <i>Max Arrivals</i> habis.`],
  ["warmup", "Warm-up Period", "Run Setup", ["Warm-up Period", "Warm-up"],
   `Periode awal yang <b>statistiknya dibuang</b>. Sistem biasanya mulai dalam keadaan kosong dan menganggur, yang tidak mewakili kondisi normal. Untuk mempelajari kondisi jangka panjang (<i>steady state</i>), statistik baru dikumpulkan setelah warm-up.
    Untuk sistem yang memang mulai kosong setiap hari, seperti bank yang buka jam 8, warm-up tidak perlu.`],
  ["terminating", "Terminating Condition", "Run Setup", ["Terminating Condition"],
   `Kondisi yang menghentikan replikasi, misalnya <code>NC(Selesai) &gt;= 1000</code>, yaitu berhenti setelah 1000 entity selesai.`],
  ["hours_per_day", "Hours Per Day", "Run Setup", ["Hours Per Day"], `Panjang satu "hari" saat memakai satuan Days. Defaultnya 24 jam.`],
  ["init_between", "Initialize Between Replications", "Run Setup", ["Initialize Between Replications: Statistics", "Initialize Between Replications: System"],
   `<i>Statistics</i>: statistik dikosongkan di awal tiap replikasi, sehingga setiap replikasi berdiri sendiri. <i>System</i>: entity, antrean dan variable direset. Biarkan keduanya tercentang kecuali Anda punya alasan khusus.`],
  ["batch_run", "Batch Run", "Run Setup", ["Batch Run (No Animation)"], `Menjalankan tanpa animasi supaya lebih cepat. Hasil langsung muncul di Summary.`],

  // ---- laporan
  ["summary", "Category Overview", "Laporan", ["Category Overview"],
   `Ringkasan hasil per kategori: <b>Entity</b> (pengalaman entity), <b>Process</b> (per modul Process), <b>Queue</b> (antrean), <b>Resource</b> (pemakaian resource), dan <b>User Specified</b> (statistik buatan Anda dari Record/Statistic).
    Kalau replikasinya lebih dari satu, angkanya adalah rata-rata dari semua replikasi.`],
  ["number_in", "Number In / Number Out", "Laporan", ["Number In", "Number Out"],
   `Jumlah entity yang masuk atau keluar. Selisihnya adalah entity yang masih di dalam saat run berakhir (WIP). Kalau Number Out jauh lebih kecil dari Number In, sistem mungkin <b>kewalahan</b>.`],
  ["wip", "WIP (Work in Process)", "Laporan", ["WIP (end)", "WIP"],
   `Jumlah entity yang <b>sedang berada di dalam</b> sistem atau modul. WIP yang terus naik sepanjang run menandakan kedatangan lebih cepat daripada kemampuan melayani.`],
  ["va_time", "VA Time (Value-Added)", "Laporan", ["VA Time", "Accum VA Time", "VA Cost"],
   `Waktu aktivitas yang <b>menambah nilai</b> bagi pelanggan, misalnya dilayani teller atau diperiksa dokter. Berasal dari Process dengan Allocation <i>Value Added</i>.`],
  ["nva_time", "NVA Time (Non-Value-Added)", "Laporan", ["NVA Time", "Accum NVA Time", "NVA Cost"],
   `Waktu aktivitas yang <b>perlu tetapi tidak menambah nilai</b>, misalnya inspeksi atau pengisian formulir.`],
  ["wait_time", "Wait Time", "Laporan", ["Wait Time", "Accum Wait Time", "Wait Cost"],
   `Waktu entity <b>menunggu</b>, terutama di antrean. Di laporan Entity, ini adalah total waktu menunggu per entity di seluruh sistem.`],
  ["transfer_time", "Transfer Time", "Laporan", ["Transfer Time", "Accum Transfer Time", "Transfer Cost"], `Waktu berpindah antar lokasi, misalnya dibawa transporter atau conveyor, atau Route.`],
  ["other_time", "Other Time", "Laporan", ["Other Time", "Accum Other Time", "Other Cost"], `Waktu aktivitas dengan Allocation <i>Other</i>.`],
  ["total_time", "Total Time", "Laporan", ["Total Time", "Max Total Time", "Total Cost"],
   `Jumlah semua jenis waktu, yaitu <b>lama entity di sistem</b> (di laporan Entity) atau lama di modul Process termasuk antre (di laporan Process).
    Rasio Wait Time dibanding Total Time menunjukkan berapa persen waktu pelanggan habis untuk menunggu.`],
  ["accum_time", "Accumulated Time", "Laporan", ["Accumulated Time"],
   `Jumlah waktu dari <b>semua</b> entity, bukan rata-rata per entity. Berguna untuk melihat ke mana total jam kerja atau jam tunggu terpakai.`],
  ["waiting_time", "Waiting Time (Queue)", "Laporan", ["Waiting Time (avg)", "Waiting Time", "Max Waiting Time"],
   `Rata-rata <b>lama menunggu di antrean</b> per entity yang sudah keluar dari antrean. Entity yang langsung dilayani tetap dihitung dengan waktu tunggu 0.`],
  ["number_waiting", "Number Waiting", "Laporan", ["Number Waiting (avg)", "Number Waiting", "Max Number Waiting"],
   `Rata-rata <b>panjang antrean terhadap waktu</b> (time-average). Contoh: kalau antrean berisi 4 orang selama setengah waktu dan kosong selama setengah waktu lainnya, Number Waiting = 2.
    Lihat juga <a data-term="little">Hukum Little</a>.`],
  ["inst_util", "Instantaneous Utilization", "Laporan", ["Instantaneous Utilization", "Utilization", "Inst Util"],
   `Rata-rata terhadap waktu dari (unit sibuk ÷ unit tersedia) <b>pada setiap saat</b>. Angka 80% berarti resource sibuk sekitar 80% dari waktu.
    <ul><li><b>Di atas ~85–90%</b>: antrean cenderung panjang dan sangat sensitif terhadap sedikit kenaikan kedatangan.</li>
    <li><b>Di bawah ~30%</b>: resource banyak menganggur; mungkin kapasitasnya berlebih.</li>
    <li><b>Mendekati 100%</b>: sistem tidak sanggup; antrean akan terus bertambah.</li></ul>`],
  ["sched_util", "Scheduled Utilization", "Laporan", ["Scheduled Utilization", "Sched Util"],
   `<b>Number Busy ÷ Number Scheduled</b>, yaitu rata-rata unit sibuk dibagi rata-rata unit tersedia. Untuk kapasitas tetap, nilainya sama dengan Instantaneous Utilization.
    Kalau kapasitas berubah menurut jadwal, kedua angka bisa berbeda. Scheduled Utilization menjawab "berapa persen kapasitas yang dibayar benar-benar terpakai".`],
  ["number_busy", "Number Busy", "Laporan", ["Number Busy", "Num Busy"],
   `Rata-rata jumlah unit resource yang <b>sedang bekerja</b> terhadap waktu. Contoh: 1.6 dari 2 teller.`],
  ["number_sched", "Number Scheduled", "Laporan", ["Number Scheduled", "Num Sched"],
   `Rata-rata jumlah unit resource yang <b>tersedia</b> (kapasitas) terhadap waktu. Untuk kapasitas tetap 2, nilainya 2.`],
  ["seized", "Total Number Seized", "Laporan", ["Total Number Seized", "Num Seized"],
   `Berapa kali resource diambil, kira-kira sama dengan jumlah entity yang dilayani.`],
  ["res_states", "% Busy / % Idle", "Laporan", ["% Busy", "% Idle", "% Inactive", "% Failed"],
   `Persentase waktu resource berada di tiap status: <b>Busy</b> (sedang dipakai), <b>Idle</b> (tersedia tetapi menganggur), <b>Inactive</b> (kapasitas 0 karena jadwal), <b>Failed</b> (rusak).`],
  ["costs", "Busy / Idle / Usage Cost", "Laporan", ["Busy Cost", "Idle Cost", "Usage Cost", "Holding Cost / Hour"],
   `Biaya resource. <i>Busy/Hour</i> dikali jam sibuk, <i>Idle/Hour</i> dikali jam menganggur, dan <i>Per Use</i> dikali berapa kali dipakai.
    Biaya entity mencakup <i>Holding Cost</i> (biaya entity berada di sistem per jam) ditambah biaya resource yang sedang dipakainya, dikelompokkan menurut jenis waktu (VA, Wait, …).`],
  ["half_width", "Half Width", "Laporan", ["Half width", "Half Width", "95% half width"],
   `Setengah lebar <b>selang kepercayaan 95%</b>. Kalau Waiting Time = 7.0 dengan half width 0.5, kita 95% yakin rata-rata sebenarnya ada di antara 6.5 dan 7.5.
    <ul><li>Half width besar (misalnya lebih dari 10% rata-rata) berarti hasilnya kurang presisi. Tambah replikasi atau perpanjang run.</li>
    <li>Dengan 1 replikasi, half width dihitung dari <i>batch means</i> dalam run itu. Kalau datanya kurang, tertulis <i>Insufficient</i> atau "–". Kalau nilai-nilai yang berurutan terlalu saling berkaitan (misalnya waktu tunggu pelanggan yang berurutan), tertulis <i>Correlated</i>. Untuk keduanya, solusinya menambah replikasi.</li>
    <li>Dua skenario baru bisa disebut berbeda kalau selangnya tidak saling tumpang tindih.</li></ul>`],
  ["avg_min_max", "Average / Minimum / Maximum", "Laporan", ["Average", "Min", "Max", "Final"],
   `<b>Average</b>: rata-rata. <b>Min/Max</b>: nilai terkecil dan terbesar yang pernah terjadi; berguna untuk melihat kasus terburuk. <b>Final</b>: nilai di akhir run.
    Untuk lebih dari satu replikasi, angka-angka ini dirata-ratakan antar replikasi.`],
  ["observations", "Observations", "Laporan", ["Observations", "Number Obs"],
   `Berapa banyak nilai yang dicatat. Rata-rata dari sedikit observasi kurang bisa dipercaya.`],
  ["tally", "Tally (statistik per observasi)", "Laporan", ["Tally"],
   `Statistik yang dicatat <b>setiap kali entity lewat</b>, misalnya waktu tunggu tiap pelanggan. Rata-ratanya adalah rata-rata per entity: jumlah nilai dibagi jumlah observasi.`],
  ["time_persistent", "Time-Persistent (rata-rata terhadap waktu)", "Laporan", ["Time Persistent", "Time-Persistent"],
   `Statistik dari nilai yang <b>berlaku sepanjang waktu</b>, misalnya panjang antrean atau jumlah resource sibuk. Rata-ratanya diberi bobot lamanya nilai itu bertahan.
    Contoh: antrean 10 selama 1 menit lalu 0 selama 9 menit menghasilkan rata-rata 1, bukan 5.`],
  ["counter", "Counter", "Laporan", ["Counter"], `Jumlah hitungan dari modul Record tipe Count, misalnya jumlah pasien yang selesai.`],
  ["output", "Output", "Laporan", ["Output"],
   `Expression yang dihitung <b>sekali di akhir run</b>, misalnya throughput per hari <code>NC(Selesai) / (TFIN / 1440)</code>.`],
  ["frequency", "Frequency", "Laporan", ["Frequency", "Category", "Standard Percent", "Restricted Percent", "Average Time"],
   `Distribusi <b>persentase waktu</b> yang dihabiskan pada tiap nilai atau kategori. Contoh: berapa persen waktu 0, 1, 2 atau 3 dokter sibuk.
    <ul><li><b>Number Obs</b>: berapa kali masuk ke kategori itu.</li>
    <li><b>Average Time</b>: rata-rata lama sekali berada di kategori itu.</li>
    <li><b>Standard Percent</b>: persen dari seluruh waktu.</li>
    <li><b>Restricted Percent</b>: persen setelah kategori yang di-<i>Exclude</i> tidak dihitung.</li></ul>`],

  // ---- teori
  ["little", "Hukum Little (L = λW)", "Teori", ["Little"],
   `Untuk sistem yang stabil: <b>rata-rata jumlah di antrean = laju kedatangan × rata-rata waktu menunggu</b>, atau L = λ × W.
    Contoh: 0.2 pelanggan per menit × 5 menit menunggu = rata-rata 1 orang di antrean. Rumus ini berguna untuk <b>memeriksa</b> apakah hasil simulasi masuk akal.`],
  ["rho", "Intensitas lalu lintas (ρ)", "Teori", ["rho"],
   `ρ = laju kedatangan × waktu layanan rata-rata ÷ jumlah server. Contoh: datang tiap 5 menit, dilayani 4 menit, 1 server memberi ρ = 4/5 = 0.8.
    Utilization hasil simulasi seharusnya mendekati ρ. Kalau ρ ≥ 1, antrean tumbuh tanpa batas.
    Waktu tunggu naik <b>tajam</b> ketika ρ mendekati 1: dari 80% ke 90% waktu tunggu kira-kira menjadi 2 kali lipat lebih.`],
  ["steady", "Steady state vs terminating", "Teori", ["steady state"],
   `<b>Terminating</b>: sistem punya awal dan akhir alami, misalnya bank buka jam 8–16. Jalankan sepanjang periode itu dengan beberapa replikasi.
    <b>Steady state</b>: sistem berjalan terus, misalnya pabrik 24 jam atau IGD. Pakai run panjang dan <a data-term="warmup">warm-up</a> supaya keadaan awal yang kosong tidak membiaskan hasil.`],
  ["validation", "Verifikasi & validasi", "Teori", [],
   `<b>Verifikasi</b>: apakah model berjalan sesuai yang kita maksud? Periksa animasi, cek dengan Hukum Little atau ρ, dan coba kasus sederhana yang jawabannya diketahui.
    <b>Validasi</b>: apakah model mewakili sistem nyata? Bandingkan dengan data sebenarnya.`],

  // ---- fungsi ekspresi
  ["fn_dist", "Distribusi: EXPO, TRIA, UNIF, NORM, …", "Fungsi & distribusi", ["EXPO", "TRIA", "UNIF", "NORM"],
   `<ul><li><code>EXPO(rata2)</code>: eksponensial; cocok untuk waktu antar kedatangan acak.</li>
    <li><code>TRIA(min, paling mungkin, max)</code>: segitiga; cocok kalau hanya tahu perkiraan minimal, biasa dan maksimal.</li>
    <li><code>UNIF(min, max)</code>: semua nilai di antara min dan max sama peluangnya.</li>
    <li><code>NORM(rata2, simpangan baku)</code>: normal; hati-hati, nilainya bisa negatif.</li>
    <li><code>ERLA(rata2, k)</code>, <code>GAMM</code>, <code>WEIB</code>, <code>LOGN</code>, <code>BETA</code>: distribusi lain.</li>
    <li><code>DISC(p1, v1, p2, v2, …)</code>: nilai diskrit dengan peluang kumulatif, misalnya <code>DISC(0.3, 1, 1.0, 2)</code> memberi 1 dengan peluang 30% dan 2 dengan peluang 70%.</li></ul>`],
  ["fn_sys", "Fungsi sistem: TNOW, NQ, NR, MR, NC, …", "Fungsi & distribusi", ["NQ", "NR", "MR", "NC", "TFIN"],
   `<ul><li><code>TNOW</code>: waktu simulasi sekarang. <code>TFIN</code>: waktu akhir run.</li>
    <li><code>NQ(Process 1.Queue)</code>: jumlah entity di antrean.</li>
    <li><code>NR(Teller)</code>: jumlah unit Teller yang sedang sibuk. <code>MR(Teller)</code>: kapasitas Teller.</li>
    <li><code>NC(nama counter)</code>: nilai counter.</li>
    <li><code>TAVG(nama tally)</code>, <code>DAVG(nama statistik)</code>: rata-rata statistik.</li>
    <li>Operator: <code>==</code> sama dengan, <code>&lt;&gt;</code> tidak sama, <code>&amp;&amp;</code> dan, <code>||</code> atau.</li></ul>`],
  ["scenarios", "Scenarios (Process Analyzer)", "Alat", ["Scenarios", "Process Analyzer", "Control", "Response"],
   `Membandingkan beberapa versi model sekaligus (menu <b>Tools → Scenarios</b>). <b>Control</b> adalah input yang diubah antar skenario (kapasitas resource, nilai awal variable, waktu antar-kedatangan); <b>response</b> adalah hasil yang dibandingkan (utilisasi, waiting time, total time, counter).
    Setiap skenario dijalankan dengan replikasinya sendiri; hasilnya rata-rata ± <a data-term="half_width">half width</a>. Jika selang kepercayaan dua skenario tidak bertumpuk, perbedaannya cukup meyakinkan.`],
  ["input_analyzer", "Input Analyzer", "Alat", ["Input Analyzer", "Fit All", "Square Error"],
   `Mencari distribusi yang cocok untuk data pengamatan (menu <b>Tools → Input Analyzer</b>). Tempel datanya, lalu <b>Fit All</b>: setiap distribusi diberi <b>square error</b> (selisih histogram data dengan distribusi; makin kecil makin cocok), uji <b>chi-square</b> dan uji <b>Kolmogorov-Smirnov (K-S)</b>.
    p-value ≥ 0.05 berarti data <i>konsisten</i> dengan distribusi itu. Expression hasilnya, misalnya <code>2.3 + GAMM(2.49, 1.07)</code>, bisa langsung dipakai di Create atau Process. Kumpulkan minimal 30 data agar hasilnya bisa dipercaya.`],
  ["expr_builder", "Expression Builder (ƒx)", "Alat", ["Expression Builder", "Build Expression", "ƒx"],
   `Setiap kolom expression punya tombol <b>ƒx</b> (atau klik kanan pada kolomnya) untuk membuka Expression Builder, seperti <i>Build Expression</i> di Arena.
    Pilih kategori (Distribusi, Variable &amp; Attribute, Resource, Antrean, Statistik, Waktu &amp; entity, Matematika, Operator), isi parameternya, lalu <b>Sisipkan</b>; hasilnya masuk di posisi kursor pada <i>Current Expression</i>.
    Untuk <code>DISC</code> dan <code>CONT</code> cukup isi tabel nilai dan peluang (%); peluang kumulatifnya dihitung otomatis. Expression yang sering dipakai bisa diberi nama di data module <b>Expression</b>, lalu cukup ditulis namanya.`],
  ["presentation", "Layar presentasi", "Alat", ["Presentasi", "Layar presentasi", "Proyektor"],
   `Tools → <b>🖥 Layar presentasi (2 layar)</b> membuka jendela kedua untuk proyektor atau monitor kedua (atur display sebagai <i>Extend</i>, bukan <i>Duplicate</i>). Jendela itu menampilkan model, animasi, jam simulasi, dan plot dengan ukuran besar; di Chrome jendelanya bisa langsung pindah ke layar lain (izinkan <i>window management</i>). Klik <b>⛶ Layar penuh</b> di sana.
    Run, Pause, Step, dan kecepatan dikendalikan dari editor di laptop. Bar <b>Presentasi</b> di bawah kanvas memilih yang dilihat penonton: <b>Editor</b> (mengikuti editor: kanvas plus panel modul, Spreadsheet/Summary/Report, dan dialog yang sedang terbuka, lengkap dengan isian yang sedang diketik; kolom yang sedang diedit diberi garis kuning), <b>Animasi</b> (model dan animasi saja, layar penuh), atau <b>Hasil</b> (Summary; ikut scroll panel Summary di laptop). A− / A+ mengubah ukuran tulisan panel. Mouse di atas kanvas tampil sebagai titik merah (<b>● Pointer</b>). <b>🔍 Ikuti zoom</b> membuat layar presentasi mengikuti zoom dan geser kanvas di laptop; matikan untuk selalu menampilkan seluruh model. <b>🔦 Sorot</b>: klik module di kanvas laptop, layar presentasi menggelapkan bagian lain (Shift+klik menambah module, klik area kosong menghapus sorotan). <b>✏ Pena</b>: gambar di atas model dengan mouse untuk melingkari atau memberi panah; coretan tampil di kedua layar dan hilang sendiri setelah sekitar 6 detik (🧽 menghapus semua, Esc mematikan pena).`],
  ["bulk_check", "Periksa banyak laporan", "Alat", ["Periksa banyak laporan", "Cek tugas", "Plagiarisme"],
   `File → <b>Periksa banyak laporan…</b> untuk dosen: seret semua file laporan (.html), satu folder, atau file <b>.zip</b> hasil "download all submissions" dari LMS. Setiap laporan dicek kode verifikasinya, lalu ditampilkan dalam tabel (NIM, nama, kelas, model, Model ID, replikasi) yang bisa diurutkan dan diunduh sebagai CSV.
    Kolom <b>Perlu dicek</b> menandai: kode tidak cocok (laporan diubah), Model ID sama dengan NIM lain (satu file model dipakai beberapa mahasiswa), tata letak module identik dengan NIM lain, NIM lain di riwayat penulis model, dan lebih dari satu laporan dari NIM yang sama. Tanda ini bukan bukti menyalin: kerja kelompok atau model awal dari dosen juga bisa membuatnya. Klik baris untuk detail dan membuka modelnya. Semua diperiksa di browser; tidak ada file yang diunggah.`],
  ["report_code", "Laporan & kode verifikasi", "Alat", ["Kode verifikasi", "Laporan", "Watermark", "Identitas"],
   `<b>File → Laporan HTML / PDF</b> membuat laporan berisi identitas (Nama, NIM, Kelas), diagram model, Run Setup, hasil, dan perbandingan skenario. Setiap halaman diberi <b>watermark</b> nama, NIM dan <b>kode verifikasi</b>.
    Kode dihitung dari seluruh isi file: jika laporan diubah setelah dibuat, <b>File → Periksa laporan</b> akan menyatakan kodenya tidak cocok. Model juga mencatat <b>Model ID</b> dan riwayat NIM yang pernah menyimpannya. Kumpulkan file laporan apa adanya (jangan disimpan ulang dari browser).`],
];
const GLOSS_BY_ID = Object.fromEntries(GLOSS.map(g => [g[0], g]));
const ALIAS = {};
for (const [id, term, , aliases] of GLOSS) for (const a of [term, ...aliases]) ALIAS[a.toLowerCase()] ??= id;
const termOf = text => ALIAS[String(text).trim().toLowerCase()];

// A column header or label that has a glossary entry becomes a link to it.
function termHtml(text) {
  const id = termOf(text);
  return id ? `<span class="term" data-term="${id}" tabindex="0" title="${esc(plain(GLOSS_BY_ID[id][4]).slice(0, 160))}…">${esc(text)}</span>` : esc(text);
}
const plain = html => html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();

// ======================= help drawer =======================
const helpEl = document.createElement("aside");
helpEl.id = "help"; helpEl.hidden = true; helpEl.setAttribute("aria-label", "Help");
helpEl.innerHTML = `<div class="helphead"><b>Help &amp; istilah</b><span style="flex:1"></span><button id="helpclose" title="Tutup (Esc)">✕</button></div>
  <input id="helpq" type="search" placeholder="Cari istilah… (mis. utilization, half width)" aria-label="Cari istilah">
  <div class="helpstart"><button id="helptour">🎓 Tutorial: model pertama</button></div>
  <div id="helplist"></div>
  <p class="hint" style="margin-top:14px">Atlverse Simulation adalah proyek independen, tidak berafiliasi dengan Rockwell Automation. Arena dan SIMAN adalah merek dagang Rockwell Automation; disebut di sini hanya untuk menjelaskan kesamaan istilah.</p>`;
document.body.appendChild(helpEl);
function openHelp(id) {
  helpEl.hidden = false; renderHelp($("helpq").value);
  if (id) {
    $("helpq").value = ""; renderHelp("");
    const e = document.getElementById("h-" + id);
    if (e) { e.open = true; e.scrollIntoView({block: "start"}); e.classList.add("flash"); setTimeout(() => e.classList.remove("flash"), 1200); }
  }
}
function renderHelp(q) {
  const list = $("helplist"); list.innerHTML = ""; q = q.trim().toLowerCase();
  let cat = null;
  for (const [id, term, c, aliases, html] of GLOSS) {
    if (q && ![term, ...aliases, plain(html)].some(s => s.toLowerCase().includes(q))) continue;
    if (c !== cat) { const h = document.createElement("h2"); h.textContent = cat = c; list.appendChild(h); }
    const d = document.createElement("details"); d.id = "h-" + id; d.open = !!q;
    d.innerHTML = `<summary>${esc(term)}</summary><div class="helpbody">${html}</div>`;
    list.appendChild(d);
  }
  if (!list.children.length) list.innerHTML = `<p class="hint">Tidak ditemukan. Coba kata lain.</p>`;
}
$("helpq").oninput = () => renderHelp($("helpq").value);
$("helpclose").onclick = () => helpEl.hidden = true;
$("helptour").onclick = () => { helpEl.hidden = true; startTour(); };
// links to terms anywhere on the page (reports, help text, interpretation)
document.addEventListener("click", ev => {
  const t = ev.target.closest("[data-term]");
  if (!t) return;
  ev.preventDefault(); ev.stopPropagation(); openHelp(t.dataset.term);
}, true);
document.addEventListener("keydown", ev => {
  if (ev.key === "F1") { ev.preventDefault(); helpEl.hidden ? openHelp() : (helpEl.hidden = true); }
  else if (ev.key === "Escape" && !helpEl.hidden && helpEl.contains(document.activeElement)) helpEl.hidden = true;
  else if (ev.key === "Enter" && ev.target.matches && ev.target.matches(".term")) openHelp(ev.target.dataset.term);
});

// header buttons
(() => {
  const h = document.createElement("button"); h.id = "bhelp"; h.textContent = "?"; h.title = "Help: penjelasan istilah (F1)"; h.setAttribute("aria-label", "Help");
  h.onclick = () => helpEl.hidden ? openHelp() : (helpEl.hidden = true);
  const t = document.createElement("button"); t.id = "btour"; t.textContent = "🎓"; t.title = "Tutorial terpandu: membuat model pertama"; t.setAttribute("aria-label", "Tutorial");
  t.onclick = () => startTour();
  $("helpbar").prepend(t, h);
  addMenuItem("help", {id: "mi-help", label: "Help & istilah", kbd: "F1", action: () => openHelp()});
  addMenuItem("help", {id: "mi-tour", label: "Tutorial terpandu…", action: () => startTour()});
  const list = $("btheme").parentElement; list.appendChild($("btheme"));   // theme last
})();

// "?" next to labels in the module dialog, Run Setup and Data tables: aria-hidden, so
// the field keeps its accessible name; F1 Help is the keyboard route.
function decorate(root) {
  for (const lab of root.querySelectorAll("label:not([data-q]), .sheet th:not([data-q])")) {
    lab.dataset.q = "1";
    const txt = [...lab.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim();
    const id = termOf(txt);
    if (!id) continue;
    const q = document.createElement("span"); q.className = "qm"; q.textContent = "?"; q.setAttribute("aria-hidden", "true");
    q.title = plain(GLOSS_BY_ID[id][4]).slice(0, 200) + "… (klik untuk penjelasan lengkap)";
    q.addEventListener("click", ev => { ev.preventDefault(); ev.stopPropagation(); openHelp(id); });
    lab.appendChild(q);
  }
  // module dialog: a one-line description of the selected module, linked to its help entry
  if (root.id === "side" && !root.querySelector(".modhelp") && typeof sel !== "undefined" && sel.size === 1) {
    const n = byId([...sel][0]), g = n && GLOSS_BY_ID["mod_" + n.type];
    const tabs = $("sidetabs");
    if (g && tabs && sideTab === "model") {
      const d = document.createElement("div"); d.className = "modhelp";
      d.innerHTML = `<b>${esc(g[1])}</b>: ${esc(plain(g[4]).split(/(?<=\.)\s/)[0])} <a href="#" data-term="${g[0]}">Selengkapnya</a>`;
      tabs.after(d);
    }
  }
}
for (const id of ["side", "setupbody", "p-sheet"]) {
  const root = $(id);
  new MutationObserver(() => decorate(root)).observe(root, {childList: true, subtree: true});
  decorate(root);
}

// ======================= reading the results =======================
const pctTxt = v => `${(v * 100).toFixed(1)}%`;
const num = v => typeof v === "number" && isFinite(v);
const UNIT_MIN = {seconds: 1 / 60, minutes: 1, hours: 60, days: 1440};
function baseOf(units) {   // value in `units` converted to the model's base time units
  const hpd = parseFloat(model.run.hours_per_day) || 24, k = u => u === "days" ? 60 * hpd : UNIT_MIN[u] || 1;
  return v => v * k(String(units || model.time_units).toLowerCase()) / k(String(model.time_units).toLowerCase());
}
function nodeFor(kind, name) {   // flat id of the module a report row belongs to
  let hit = null;
  eachNode((n, fid) => {
    if (hit) return;
    if (kind === "queue" && moduleQueue(n) === name) hit = fid;
    else if (kind === "process" && n.type === "process" && n.props.name === name) hit = fid;
    else if (kind === "resource" && has(n.type, "process", "seize") && (n.props.resources || []).some(r => r.resource === name)) hit = fid;
    else if (kind === "entity" && n.type === "create" && n.props.entity_type === name) hit = fid;
  });
  return hit;
}
function focusModule(fid) {
  if (!fid || anim) { if (anim) toast("Kembali ke mode edit (End) untuk memilih modul"); return; }
  const parts = String(fid).split("/"), n = findDeep(fid); if (!n) return;
  if (parts.slice(0, -1).join("/") !== path.join("/")) goLevel(parts.slice(0, -1));
  sel = new Set([n.id]); sideTab = "model"; render(); renderSide(); centerOn(n);
  const g = document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`);
  if (g) { g.classList.add("flash"); setTimeout(() => g.classList.remove("flash"), 1600); }
}

function insights(res) {
  const reps = res.replications, n = reps.length, r0 = reps[0], u = model.time_units, run = model.run;
  const avg = f => { const v = reps.map(x => { try { return f(x); } catch (e) { return undefined; } }).filter(num); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const out = [], link = (id, txt) => `<a href="#" data-term="${id}">${txt}</a>`;
  const warm = baseOf(run.warmup_units)(parseFloat(run.warmup) || 0), span = Math.max(1e-9, avg(x => x.time) - warm);

  out.push(["info", `Angka di laporan ${n > 1 ? `adalah <b>rata-rata dari ${n} ${link("replication", "replikasi")}</b>` : `berasal dari <b>1 ${link("replication", "replikasi")}</b>`},
    masing-masing sepanjang ${fmt(avg(x => x.time))} ${u}${warm ? `, dengan ${link("warmup", "warm-up")} ${fmt(warm)} ${u} yang statistiknya dibuang` : ""}. Satuan waktu: <b>${u}</b>.`]);
  if (n === 1) out.push(["warn", `Hanya 1 replikasi. Karena ada keacakan, hasil run berikutnya bisa berbeda. Untuk kesimpulan atau membandingkan skenario, gunakan setidaknya 5–10 replikasi (Run Setup → Number of Replications) dan lihat ${link("half_width", "half width")}-nya.`]);

  // resources
  const rs = Object.keys(r0.resources).map(k => ({k, ui: avg(x => x.resources[k].instantaneous_utilization), su: avg(x => x.resources[k].scheduled_utilization),
    nb: avg(x => x.resources[k].number_busy), ns: avg(x => x.resources[k].number_scheduled)})).filter(x => num(x.ui)).sort((a, b) => b.ui - a.ui);
  for (const x of rs.slice(0, 6)) {
    let lvl = "ok", say = "Tingkat kesibukan wajar.";
    if (x.ui >= 0.97) { lvl = "bad"; say = "Hampir selalu sibuk. Kapasitas kemungkinan <b>tidak cukup</b> dan antrean bisa terus memanjang. Tambah kapasitas atau percepat layanan."; }
    else if (x.ui >= 0.85) { lvl = "warn"; say = `Sangat sibuk. Antrean cenderung panjang dan sangat peka terhadap kenaikan kedatangan (lihat ${link("rho", "ρ")}).`; }
    else if (x.ui < 0.3) { lvl = "info"; say = "Banyak menganggur. Kapasitasnya mungkin berlebih untuk beban ini."; }
    let t = `<b>${esc(x.k)}</b> sibuk <b>${pctTxt(x.ui)}</b> dari waktu (${link("inst_util", "Instantaneous Utilization")}); rata-rata ${fmt(x.nb)} dari ${fmt(x.ns)} unit bekerja. ${say}`;
    if (num(x.su) && Math.abs(x.su - x.ui) > 0.03) t += ` ${link("sched_util", "Scheduled Utilization")} ${pctTxt(x.su)} berbeda karena kapasitasnya berubah selama run, misalnya karena jadwal atau ALTER.`;
    out.push([lvl, t, nodeFor("resource", x.k)]);
  }

  // queues and Little's law
  const qs = Object.keys(r0.queues).filter(q => !q.startsWith("__")).map(q => ({q, w: avg(x => x.queues[q].waiting_time.average), wmax: avg(x => x.queues[q].waiting_time.max),
    L: avg(x => x.queues[q].number_waiting.average), lam: avg(x => x.queues[q].waiting_time.observations / span)})).filter(x => num(x.w)).sort((a, b) => b.w - a.w);
  if (qs.length) {
    const x = qs[0];
    let t = `Antrean terlama: <b>${esc(x.q)}</b>. Entity menunggu rata-rata <b>${fmt(x.w)} ${u}</b> (${link("waiting_time", "Waiting Time")}), paling lama ${fmt(x.wmax)} ${u}, dan rata-rata ada ${fmt(x.L)} entity yang mengantre (${link("number_waiting", "Number Waiting")}).`;
    if (num(x.lam) && x.lam > 0 && x.L > 0.01) {
      const lw = x.lam * x.w, ok = Math.abs(lw - x.L) / x.L < 0.1;
      t += `<br>Cek dengan ${link("little", "Hukum Little")}: λ × W = ${fmt(x.lam)} per ${u.replace(/s$/, "")} × ${fmt(x.w)} = <b>${fmt(lw)}</b>, ${ok ? `hampir sama dengan Number Waiting ${fmt(x.L)} ✓` : `berbeda dari Number Waiting ${fmt(x.L)}. Ini wajar kalau run pendek atau masih banyak entity mengantre di akhir run.`}`;
    }
    out.push([x.w > 0 ? "info" : "ok", t, nodeFor("queue", x.q)]);
    if (qs.length > 1) out.push(["info", `Antrean lain, diurutkan dari waktu tunggu terlama: ${qs.slice(1, 6).map(y => `${esc(y.q)} ${fmt(y.w)}`).join(", ")} ${u}.`]);
  }

  // entities: where does the time go, and is the system keeping up?
  for (const t of Object.keys(r0.entities.in_ || {}).slice(0, 4)) {
    const tt = avg(x => x.tallies[`${t}.TotalTime`].average), w = avg(x => x.tallies[`${t}.wait_time`].average);
    const ein = avg(x => x.entities.in_[t]), eout = avg(x => x.entities.out[t]) || 0, wip = avg(x => x.entities.wip[t]) || 0;
    const name = t === "null" ? "(tanpa tipe)" : t;
    if (num(tt) && tt > 0) {
      const pw = num(w) ? w / tt : 0;
      out.push([pw > 0.5 ? "warn" : "info", `Entity <b>${esc(name)}</b> rata-rata berada <b>${fmt(tt)} ${u}</b> di sistem (${link("total_time", "Total Time")}). ${pctTxt(pw)} dari waktu itu habis untuk <b>menunggu</b> (${link("wait_time", "Wait Time")})${pw > 0.5 ? ", lebih lama daripada waktu dilayani" : ""}.`, nodeFor("entity", t)]);
    }
    if (num(ein) && ein > 20 && wip > Math.max(5, 0.05 * ein))
      out.push(["bad", `Di akhir run masih ada sekitar ${fmt(wip)} entity <b>${esc(name)}</b> di dalam sistem (masuk ${fmt(ein)}, keluar ${fmt(eout)}). Kalau jumlah ini terus naik ketika run diperpanjang, sistem <b>tidak stabil</b>: kedatangan lebih cepat daripada kapasitas melayani.`, nodeFor("entity", t)]);
  }

  // precision
  const hws = [];
  const hwOf = (key, single) => n > 1 ? (res.across[key] || {}).half_width : single;
  for (const t of Object.keys(r0.entities.in_ || {})) { const a = avg(x => x.tallies[`${t}.TotalTime`].average); if (num(a) && a > 0) hws.push([`Total Time ${t}`, a, hwOf(`tallies.${t}.TotalTime`, (r0.tallies[`${t}.TotalTime`] || {}).half_width)]); }
  for (const x of qs.slice(0, 3)) if (x.w > 0) hws.push([`Waiting Time ${x.q}`, x.w, hwOf(`queues.${x.q}`, r0.queues[x.q].waiting_time.half_width)]);
  const known = hws.filter(h => num(h[2]));
  if (known.length) {
    const worst = known.map(h => [...h, h[2] / h[1]]).sort((a, b) => b[3] - a[3])[0];
    out.push(worst[3] > 0.1
      ? ["warn", `Presisi: ${link("half_width", "half width")} ${esc(worst[0])} adalah ±${fmt(worst[2])} (${pctTxt(worst[3])} dari rata-ratanya ${fmt(worst[1])}). Hasilnya belum presisi; tambah replikasi atau perpanjang run.`]
      : ["ok", `Presisi baik: ${link("half_width", "half width")} statistik utama ≤ 10% dari rata-ratanya (terbesar: ${esc(worst[0])} ${fmt(worst[1])} ± ${fmt(worst[2])}).`]);
  } else if (hws.length) out.push(["info", `${link("half_width", "Half width")} tidak tersedia karena data dalam 1 replikasi terlalu sedikit untuk menghitungnya. Tambah replikasi.`]);

  for (const k of Object.keys(r0.frequencies || {}).slice(0, 3)) {
    const f = r0.frequencies[k], top = Object.entries(f).sort((a, b) => b[1].standard_percent - a[1].standard_percent)[0];
    if (top) out.push(["info", `${link("frequency", "Frequency")} <b>${esc(k)}</b>: nilai yang paling lama terjadi adalah <b>${esc(top[0])}</b> (${top[1].standard_percent.toFixed(1)}% dari waktu, replikasi 1).`]);
  }
  return out;
}

// ======================= charts =======================
const SVGNS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs, parent) { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.appendChild(e); return e; }
function chartBox(after, title) {
  const d = document.createElement("div"); d.className = "chart";
  if (title) { const h = document.createElement("div"); h.className = "charttitle"; h.textContent = title; d.appendChild(h); }
  after.after(d); return d;
}
// horizontal bars; items: {label, value, text, color, fid, title}
function hbars(box, items, max) {
  const rowH = 22, lw = 170, w = 600, h = items.length * rowH + 4;
  const s = svgEl("svg", {viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": box.firstChild ? box.firstChild.textContent : "chart"}, box);
  max = max || Math.max(1e-12, ...items.map(i => i.value));
  items.forEach((it, i) => {
    const y = i * rowH + 2, g = svgEl("g", {class: it.fid ? "bar click" : "bar"}, s);
    svgEl("text", {x: lw - 6, y: y + 14, "text-anchor": "end", class: "lab"}, g).textContent = it.label.length > 26 ? it.label.slice(0, 25) + "…" : it.label;
    svgEl("rect", {x: lw, y: y + 3, width: w - lw - 70, height: rowH - 8, class: "track", rx: 3}, g);
    svgEl("rect", {x: lw, y: y + 3, width: Math.max(1, (w - lw - 70) * Math.min(1, it.value / max)), height: rowH - 8, fill: it.color || "var(--accent)", rx: 3}, g);
    svgEl("text", {x: w - 64, y: y + 14, class: "val"}, g).textContent = it.text;
    svgEl("title", {}, g).textContent = (it.title || `${it.label}: ${it.text}`) + (it.fid ? " · klik untuk menyorot modulnya" : "");
    if (it.fid) g.addEventListener("click", () => focusModule(it.fid));
  });
}
// stacked horizontal bars: items {label, parts: [[name, value, color]], fid}
function stacked(box, items, unit) {
  const rowH = 24, lw = 170, w = 600, h = items.length * rowH + 26;
  const s = svgEl("svg", {viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": "Komposisi waktu"}, box);
  const max = Math.max(1e-12, ...items.map(i => i.parts.reduce((a, p) => a + p[1], 0)));
  items.forEach((it, i) => {
    const y = i * rowH + 2, g = svgEl("g", {class: it.fid ? "bar click" : "bar"}, s);
    svgEl("text", {x: lw - 6, y: y + 15, "text-anchor": "end", class: "lab"}, g).textContent = it.label.length > 26 ? it.label.slice(0, 25) + "…" : it.label;
    let x = lw; const tot = it.parts.reduce((a, p) => a + p[1], 0);
    for (const [name, v, c] of it.parts) {
      if (!(v > 0)) continue;
      const bw = (w - lw - 70) * v / max;
      const r = svgEl("rect", {x, y: y + 3, width: Math.max(.5, bw), height: rowH - 8, fill: c}, g);
      svgEl("title", {}, r).textContent = `${it.label} · ${name}: ${fmt(v)} ${unit} (${pctTxt(v / tot)})`;
      x += bw;
    }
    svgEl("text", {x: w - 64, y: y + 15, class: "val"}, g).textContent = fmt(tot);
    if (it.fid) g.addEventListener("click", () => focusModule(it.fid));
  });
  const legend = [...new Map(items.flatMap(i => i.parts.filter(p => p[1] > 0).map(p => [p[0], p[2]]))).entries()];
  let lx = lw; const ly = items.length * rowH + 12;
  for (const [name, c] of legend) { svgEl("rect", {x: lx, y: ly - 8, width: 10, height: 10, fill: c, rx: 2}, s); svgEl("text", {x: lx + 14, y: ly + 1, class: "lab"}, s).textContent = name; lx += 24 + name.length * 6.5; }
}
// vertical histogram for a Frequency
function histogram(box, cats) {
  const w = 600, h = 150, pad = 26, bw = Math.min(60, (w - 2 * pad) / Math.max(1, cats.length) - 6);
  const s = svgEl("svg", {viewBox: `0 0 ${w} ${h + 20}`, role: "img", "aria-label": "Histogram"}, box);
  const max = Math.max(1e-12, ...cats.map(c => c[1]));
  cats.forEach(([lab, v], i) => {
    const x = pad + i * (bw + 6), bh = (h - 30) * v / max;
    const r = svgEl("rect", {x, y: h - bh, width: bw, height: Math.max(.5, bh), fill: "var(--accent)", rx: 2}, s);
    svgEl("title", {}, r).textContent = `${lab}: ${v.toFixed(2)}% dari waktu`;
    svgEl("text", {x: x + bw / 2, y: h - bh - 4, "text-anchor": "middle", class: "val"}, s).textContent = `${v.toFixed(1)}%`;
    svgEl("text", {x: x + bw / 2, y: h + 14, "text-anchor": "middle", class: "lab"}, s).textContent = String(lab).slice(0, 10);
  });
}
const utilColor = v => v >= 0.97 ? "var(--err)" : v >= 0.85 ? "var(--warn)" : v < 0.3 ? "var(--off)" : "var(--create)";
const CAT_COLORS = [["VA", "va", "#2563eb"], ["NVA", "nva", "#7e3af2"], ["Wait", "wait", "#f59e0b"], ["Transfer", "tran", "#0694a2"], ["Other", "other", "#9aa4b2"]];

function learnSummary(res) {
  const p = $("p-summary"), reps = res.replications, r0 = reps[0], u = model.time_units;
  const avg = f => { const v = reps.map(x => { try { return f(x); } catch (e) { return undefined; } }).filter(num); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0; };
  // 1. plain-language reading
  const box = document.createElement("div"); box.id = "sum-learn"; box.className = "learn";
  box.innerHTML = `<div class="learnhead"><b>📘 Cara membaca hasil ini</b><button class="learnfold" aria-expanded="true" title="Sembunyikan / tampilkan">▾</button></div>`;
  const ul = document.createElement("ul");
  for (const [lvl, html, fid] of insights(res)) {
    const li = document.createElement("li"); li.className = lvl; li.innerHTML = html;
    if (fid) { const b = document.createElement("button"); b.className = "goto"; b.textContent = "lihat modul"; b.onclick = () => focusModule(fid); li.append(" ", b); }
    ul.appendChild(li);
  }
  box.appendChild(ul);
  const foot = document.createElement("p"); foot.className = "hint";
  foot.innerHTML = `Istilah bergaris titik-titik bisa diklik untuk melihat penjelasannya. Klik batang grafik atau baris tabel untuk menyorot modulnya di kanvas. Daftar semua istilah: <a href="#" data-term="summary">Help (F1)</a>.`;
  box.appendChild(foot);
  box.querySelector(".learnfold").onclick = ev => { const open = ul.hidden; ul.hidden = foot.hidden = !open; ev.target.setAttribute("aria-expanded", String(open)); ev.target.textContent = open ? "▾" : "▸"; };
  ($("sum-top") || p.firstChild).after(box);

  // 2. charts at the start of each section
  const ents = Object.keys(r0.entities.in_ || {});
  if ($("sum-entity") && ents.length) stacked(chartBox($("sum-entity"), `Rata-rata waktu per entity (${u}): dilayani vs menunggu`),
    ents.map(t => ({label: t === "null" ? "(none)" : t, fid: nodeFor("entity", t), parts: CAT_COLORS.map(([n, k, c]) => [n, avg(x => x.tallies[`${t}.${k}_time`].average), c])})), u);
  const procs = allNodes().filter(nd => nd.type === "process" && nd.props.type !== "Submodel" && r0.counters[`${nd.props.name}.NumberIn`] !== undefined).map(nd => nd.props.name);
  if ($("sum-process") && procs.length) stacked(chartBox($("sum-process"), `Waktu per entity di tiap Process (${u})`),
    procs.map(pn => ({label: pn, fid: nodeFor("process", pn), parts: [["VA", "VA", "#2563eb"], ["NVA", "NVA", "#7e3af2"], ["Wait", "Wait", "#f59e0b"], ["Transfer", "Transfer", "#0694a2"], ["Other", "Other", "#9aa4b2"]]
      .map(([n, k, c]) => [n, avg(x => x.tallies[`${pn}.${k}TimePerEntity`].average), c])})), u);
  const qs = Object.keys(r0.queues).filter(q => !q.startsWith("__"));
  if ($("sum-queue") && qs.length) hbars(chartBox($("sum-queue"), `Rata-rata waktu menunggu di antrean (${u})`),
    qs.map(q => { const w = avg(x => x.queues[q].waiting_time.average); return {label: q, value: w, text: fmt(w), fid: nodeFor("queue", q), color: "#f59e0b"}; }));
  const rk = Object.keys(r0.resources);
  if ($("sum-resource") && rk.length) hbars(chartBox($("sum-resource"), "Utilization resource (hijau: wajar · kuning: ≥ 85% · merah: ≥ 97% · abu-abu: < 30%)"),
    rk.map(k => { const v = avg(x => x.resources[k].instantaneous_utilization); return {label: k, value: v, text: pctTxt(v), color: utilColor(v), fid: nodeFor("resource", k)}; }), 1);
  for (const h of p.querySelectorAll("h2")) {
    const m = /^Frequency: (.*)$/.exec(h.textContent); if (!m) continue;
    const k = m[1], cats = [...new Set(reps.flatMap(x => Object.keys((x.frequencies || {})[k] || {})))]
      .sort((a, b) => (isNaN(a) || isNaN(b)) ? String(a).localeCompare(String(b)) : a - b)
      .map(c => [c, avg(x => ((x.frequencies[k] || {})[c] || {standard_percent: 0}).standard_percent)]);
    histogram(chartBox(h.nextElementSibling || h, ""), cats);
  }
  // 3. table rows lead to their module
  const kindOf = {"sum-queue": "queue", "sum-resource": "resource", "sum-process": "process", "sum-entity": "entity"};
  let kind = null;
  for (const e of p.children) {
    if (e.tagName === "H2" && e.id) kind = kindOf[e.id] || null;
    if (kind && e.tagName === "TABLE") for (const tr of [...e.rows].slice(1)) {
      const fid = nodeFor(kind, tr.cells[0].textContent === "(none)" ? "null" : tr.cells[0].textContent);
      if (fid) { tr.classList.add("click"); tr.title = "Klik untuk menyorot modulnya di kanvas"; tr.onclick = () => focusModule(fid); }
    }
  }
}
// Summary gets the reading aids; each result remembers the model it came from (for the tutorial)
const _publish = publishResults;
publishResults = function (res) { res._model = JSON.parse(snapshot()); _publish(res); try { learnSummary(res); } catch (e) { console.warn("learnSummary", e); } };

// ======================= guided tutorials =======================
// Each step lists what it needs ([ok, "what to do"]); unmet items are shown so the student
// knows exactly what is still missing. Checks read the model, so any way of editing counts.
const norm = s => String(s ?? "").trim().toLowerCase();
const nodesOf = t => model.nodes.filter(n => n.type === t);
const named = (t, name) => model.nodes.find(n => n.type === t && norm(n.props.name) === norm(name));
const linkTo = (a, b, port = "out") => !!(a && b && model.links.some(l => l.from === a.id && l.to === b.id && l.port === port));
const usesRes = (n, r) => !!n && (n.props.resources || []).some(x => norm(x.resource) === norm(r));
const tria = (n, a, b, c, units = "Minutes") => !!n && n.props.delay_type === "Triangular" && +n.props.minimum === a && +n.props.value === b && +n.props.maximum === c && n.props.units === units;
const resAvg = (res, f) => { if (!res) return null; const v = res.replications.map(x => { try { return f(x); } catch (e) { return undefined; } }).filter(num); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
const qWait = (res, q) => resAvg(res, x => x.queues[q].waiting_time.average);
const util = (res, r) => resAvg(res, x => x.resources[r].instantaneous_utilization);
const T_ = (id, txt) => `<a href="#" data-term="${id}">${txt}</a>`;
const hourly = (sc, n) => { const rs = sc && slotsOf(sc, 1); return rs ? rs.slots.slice(0, n).join(",") : ""; };
const NEXT_OK = "Lanjut ›";

const placeStep = (title, kind, name, after, port, extra = "", needs = () => []) => ({
  title, target: `.pal[data-kind="${kind}"]`,
  body: () => `${extra}<br>Pilih modul <b>${after}</b> di kanvas, lalu klik <b>${M[kind].label}</b> di Project Bar dan klik kanvas di sebelah kanannya. Auto-Connect menyambungkannya ke ${port === "out" ? "keluaran" : `cabang <b>${port === "true" ? "True" : "False"}</b>`} ${after}.
    Klik modul baru itu dan beri Name <code>${name}</code>.`,
  need: () => {
    const a = model.nodes.find(n => norm(n.props.name) === norm(after)), b = named(kind, name);
    return [[!!b, `Ada modul ${M[kind].label} bernama "${name}"`], [linkTo(a, b, port), `"${after}" ${port === "out" ? "" : `(cabang ${port === "true" ? "True" : "False"}) `}tersambung ke "${name}". Kalau belum, tarik garis dari titik ● ${port === "out" ? "keluaran" : port === "true" ? "True (atas)" : "False (bawah)"} ke modul itu`], ...needs(b)];
  }});
const runStep = (title, reps, hours, extra = "") => ({
  title, target: "#brun",
  enter: st => { st.before = lastResults; },
  body: () => `${extra}Klik <b>⚙ Run Setup</b>: Number of Replications <code>${reps}</code>, Replication Length <code>${hours}</code> <b>Hours</b>, lalu OK.
    Setelah itu klik <b>▶ Go</b> dan <b>⏩ Fast-Forward</b>. Kalau sedang di tengah animasi, klik <b>■ End</b> dulu.`,
  need: st => {
    const r = model.run, fresh = !!lastResults && lastResults !== st.before;
    return [[+r.replications === reps && +r.length === hours && r.length_units === "Hours", `Run Setup: ${reps} replikasi × ${hours} Hours`],
            [fresh && +lastResults._model.run.replications === reps, "Jalankan sampai hasil keluar (▶ Go lalu ⏩ Fast-Forward)"]];
  }});
const newStep = (title, text) => ({title, body: () => `${text}<br><br>Model yang sedang terbuka akan diganti model baru. Model lama bisa dikembalikan dengan <kbd>Ctrl</kbd>+<kbd>Z</kbd>.`,
  start: "Mulai", onStart: () => $("bnew").click()});
const createStep = (title, etype, mean, extra = "") => ({
  title, target: '.pal[data-kind="create"]',
  body: () => `Letakkan modul <b>Create</b> (klik Create di Project Bar, lalu klik kanvas), klik modulnya, lalu isi:
    <ul><li>Entity Type: <code>${etype}</code></li><li>Type: <b>Random (Expo)</b>, Value: <code>${mean}</code>, Units: <b>Minutes</b></li></ul>${extra}`,
  need: () => { const c = nodesOf("create")[0];
    return [[!!c, "Ada modul Create di kanvas"], [!!c && norm(c.props.entity_type) === norm(etype), `Entity Type = ${etype}`],
            [!!c && c.props.type === "Random (Expo)" && +c.props.value === mean && c.props.units === "Minutes", `Random (Expo), Value ${mean}, Minutes`]]; }});

const TOURS = {
  // ---------------------------------------------------------------- 1. first model
  bank: {title: "Model pertama: antrean bank", level: "Dasar", desc: "Create → Process → Dispose, replikasi, membaca laporan, membandingkan 1 vs 2 teller.", steps: [
    newStep("Model pertama: antrean di bank", `Kita akan membuat model sederhana: <b>nasabah datang → antre ke teller → dilayani → pulang</b>, lalu menjalankannya dan membaca hasilnya.`),
    {title: "1. Tempat nasabah datang: Create", target: '.pal[data-kind="create"]',
     body: () => `Klik <b>Create</b> di Project Bar kiri, lalu klik sekali di kanvas. Modul ini juga bisa diseret ke kanvas.
       <br>${T_("mod_create", "Create")} adalah titik masuk ${T_("entity", "entity")}; di sini entity-nya adalah nasabah.`,
     need: () => [[nodesOf("create").length > 0, "Ada modul Create di kanvas"]]},
    {title: "2. Atur kedatangan", target: "#side",
     body: () => `Klik modul Create di kanvas. Dialognya muncul di panel kanan. Isi:
       <ul><li>Name: <code>Nasabah Datang</code></li><li>Entity Type: <code>Nasabah</code></li><li>Type: <b>Random (Expo)</b>, Value: <code>5</code>, Units: <b>Minutes</b></li></ul>
       Artinya rata-rata satu nasabah datang <b>tiap 5 menit</b> dengan selang yang acak (${T_("fn_dist", "EXPO")}).`,
     need: () => { const c = nodesOf("create")[0];
       return [[!!c && norm(c.props.entity_type) === "nasabah", "Entity Type = Nasabah"], [!!c && c.props.type === "Random (Expo)" && +c.props.value === 5 && c.props.units === "Minutes", "Random (Expo), Value 5, Minutes"]]; }},
    {title: "3. Tempat dilayani: Process", target: '.pal[data-kind="process"]',
     body: () => `Biarkan Create tetap terpilih, lalu klik <b>Process</b> dan klik kanvas di sebelah kanan Create. Karena <i>Auto-Connect</i> aktif, keduanya otomatis tersambung.
       <br>Kalau belum tersambung, tarik garis dari titik bulat ● di kanan Create ke Process.`,
     need: () => [[nodesOf("process").length > 0, "Ada modul Process"], [nodesOf("create").some(c => nodesOf("process").some(p => linkTo(c, p))), "Create tersambung ke Process"]]},
    {title: "4. Teller melayani nasabah", target: "#side",
     body: () => `Klik modul Process, lalu isi:
       <ul><li>Name: <code>Layanan Teller</code></li>
       <li>Action: <b>Seize Delay Release</b>, artinya ambil teller (antre kalau sibuk), dilayani, lalu lepaskan teller</li>
       <li>Di baris Resources, ganti nama resource menjadi <code>Teller</code></li>
       <li>Delay Type: <b>Triangular</b>, Minimum <code>3</code>, Value (Most Likely) <code>4</code>, Maximum <code>6</code>, Units <b>Minutes</b></li></ul>
       ${T_("resource", "Resource")} Teller jumlahnya terbatas (1), jadi nasabah akan ${T_("queue", "antre")}.`,
     need: () => { const p = named("process", "Layanan Teller");
       return [[!!p, "Name Process = Layanan Teller"], [!!p && p.props.action === "Seize Delay Release", "Action = Seize Delay Release"], [usesRes(p, "Teller"), "Resource Name = Teller"], [tria(p, 3, 4, 6), "Triangular 3 / 4 / 6 Minutes"]]; }},
    placeStep("5. Nasabah pulang: Dispose", "dispose", "Nasabah Pulang", "Layanan Teller", "out", `${T_("mod_dispose", "Dispose")} adalah titik keluar dan mencatat lama nasabah di sistem.`),
    {title: "6. Tebak dulu sebelum menjalankan",
     body: () => `Nasabah datang rata-rata tiap <b>5 menit</b> dan dilayani rata-rata (3 + 4 + 6) / 3 = <b>4.33 menit</b>. Jadi teller akan sibuk kira-kira 4.33 / 5 = <b>87%</b> dari waktu (${T_("rho", "ρ")}).
       <br><br>Pada tingkat kesibukan setinggi itu, antrean biasanya cukup panjang. Mari kita lihat apakah simulasi setuju.`},
    runStep("7. Atur run dan jalankan", 5, 8, `Lima ${T_("replication", "replikasi")} berarti lima "hari" dengan keacakan yang berbeda; 8 jam adalah satu hari kerja. `),
    {title: "8. Baca hasilnya", target: "#sum-learn",
     enter: st => { st.res1 = lastResults; },
     body: st => `Hasilnya ada di <b>Summary</b> di bawah. Kotak <b>📘 Cara membaca hasil ini</b> menjelaskan angka-angka penting.
       <ul><li>Utilization Teller: <b>${pctTxt(util(st.res1, "Teller") || 0)}</b>. Bandingkan dengan tebakan 87%. Selisih beberapa persen itu wajar: jumlah nasabah yang datang dalam 8 jam juga acak, dan teller masih menganggur di awal hari.</li>
       <li>Rata-rata menunggu: <b>${fmt(qWait(st.res1, "Layanan Teller.Queue"))} menit</b>, padahal dilayani hanya 4.33 menit.</li></ul>
       Istilah bergaris titik-titik bisa diklik untuk melihat penjelasannya.`},
    {title: "9. Eksperimen: tambah satu teller", target: '.pal.data[data-table="resources"]',
     enter: st => { st.before = lastResults; },
     body: () => `Klik <b>■ End</b> untuk kembali ke mode edit. Lalu klik <b>Resource</b> di bagian Data modules, ubah <b>Capacity</b> Teller menjadi <code>2</code>, dan jalankan lagi (<b>▶ Go</b>, lalu <b>⏩ Fast-Forward</b>).`,
     need: st => [[String((model.data.resources.Teller || {}).capacity).trim() === "2", "Capacity Teller = 2"],
       [!!lastResults && lastResults !== st.before && String(((lastResults._model.data.resources || {}).Teller || {}).capacity).trim() === "2", "Jalankan lagi dengan 2 teller"]]},
    {title: "10. Bandingkan", target: "#sum-learn",
     body: st => `<table class="res"><tr><th></th><th>1 teller</th><th>2 teller</th></tr>
       <tr><td>Utilization</td><td>${pctTxt(util(st.res1, "Teller") || 0)}</td><td>${pctTxt(util(lastResults, "Teller") || 0)}</td></tr>
       <tr><td>Waiting Time (menit)</td><td>${fmt(qWait(st.res1, "Layanan Teller.Queue"))}</td><td>${fmt(qWait(lastResults, "Layanan Teller.Queue"))}</td></tr></table>
       Kapasitas naik 2 kali lipat, tetapi waktu tunggu turun <b>jauh lebih dari setengah</b>. Antrean bersifat <b>non-linear</b>: ketika ${T_("rho", "ρ")} tinggi, sedikit tambahan kapasitas memberi dampak besar. Sebaliknya, teller sekarang lebih sering menganggur. Inilah <i>trade-off</i> yang dianalisis dengan simulasi.`},
  ]},

  // ---------------------------------------------------------------- 2. Decide
  decide: {title: "Decide: inspeksi & pengerjaan ulang", level: "Dasar", desc: "Percabangan by Chance dan by Condition, alur balik (rework loop), menghitung beban akibat rework.", steps: [
    newStep("Decide: inspeksi kualitas", `Part datang, diinspeksi, lalu <b>${T_("mod_decide", "Decide")}</b> memutuskan: <b>lulus</b> (keluar) atau <b>gagal</b> (diperbaiki lalu diinspeksi ulang).
      Anda akan belajar percabangan peluang, alur balik, dan percabangan berdasarkan kondisi.`),
    createStep("1. Part datang", "Part", 10, `Beri Name <code>Part Datang</code>. Rata-rata satu part tiap 10 menit.`),
    placeStep("2. Inspeksi", "process", "Inspeksi", "Part Datang", "out", "", p => [
      [usesRes(p, "Inspektor"), "Resources: Resource Name = Inspektor"], [tria(p, 4, 5, 7), "Delay Type Triangular 4 / 5 / 7 Minutes"]]),
    {...placeStep("3. Decide: lulus atau tidak?", "decide", "Lulus?", "Inspeksi", "out", "", d => [
      [!!d && d.props.type === "2-way by Chance", "Type = 2-way by Chance"], [!!d && +d.props.percent_true === 80, "Percent True = 80"]]),
     body: () => `Pilih <b>Inspeksi</b>, klik <b>Decide</b> di Project Bar lalu klik kanvas di kanan Inspeksi. Klik Decide itu dan isi:
       <ul><li>Name: <code>Lulus?</code></li><li>Type: <b>2-way by Chance</b></li><li>Percent True: <code>80</code></li></ul>
       Artinya 80% part keluar lewat cabang <b>True</b> (lulus), sisanya 20% lewat <b>False</b>. Decide punya dua keluaran: True (atas) dan False (bawah).`},
    placeStep("4. Part lulus keluar", "dispose", "Part Bagus", "Lulus?", "true",
      `Cabang <b>True</b> adalah part yang lulus. Karena Auto-Connect memakai keluaran pertama yang masih kosong, Dispose ini akan tersambung ke True.`),
    placeStep("5. Part gagal diperbaiki", "process", "Perbaikan", "Lulus?", "false",
      `Pilih <b>Lulus?</b> sekali lagi, lalu letakkan <b>Process</b> di bawah kanannya; Auto-Connect sekarang memakai cabang <b>False</b>. Isi Resource <code>Teknisi</code>, Delay Triangular <code>10 / 15 / 20</code> Minutes.`, p => [
      [usesRes(p, "Teknisi"), "Resources: Resource Name = Teknisi"], [tria(p, 10, 15, 20), "Delay Type Triangular 10 / 15 / 20 Minutes"]]),
    {title: "6. Alur balik: inspeksi ulang", target: "#stage",
     body: () => `Part yang sudah diperbaiki harus <b>diinspeksi lagi</b>. Tarik garis dari titik ● keluaran <b>Perbaikan</b> ke modul <b>Inspeksi</b>.
       <br>Alur balik (<i>loop</i>) seperti ini sering ada di dunia nyata: pengerjaan ulang, pasien kontrol ulang, dokumen yang dikembalikan.`,
     need: () => [[linkTo(named("process", "Perbaikan"), named("process", "Inspeksi")), "Perbaikan tersambung kembali ke Inspeksi"]]},
    {title: "7. Hitung dulu",
     body: () => `Setiap part bisa diinspeksi lebih dari sekali. Rata-rata jumlah inspeksi per part = 1 / 0.8 = <b>1.25 kali</b>.
       <ul><li>Laju inspeksi = 1.25 × (1 part / 10 menit) = 0.125 per menit.</li>
       <li>Waktu inspeksi rata-rata = (4 + 5 + 7) / 3 = 5.33 menit, jadi ${T_("rho", "utilisasi")} Inspektor ≈ 0.125 × 5.33 = <b>67%</b>, bukan 53%. Rework menambah beban!</li>
       <li>Teknisi: 0.2 × 1.25 / 10 per menit × 15 menit ≈ <b>38%</b>.</li></ul>`},
    runStep("8. Jalankan", 5, 8),
    {title: "9. Baca hasilnya", target: "#sum-learn",
     enter: st => { st.res1 = lastResults; },
     body: st => { const r = st.res1, ins = resAvg(r, x => x.counters["Inspeksi.NumberIn"]), parts = resAvg(r, x => x.entities.in_.Part);
       return `<ul><li>Inspeksi dilalui rata-rata <b>${fmt(ins)}</b> kali untuk <b>${fmt(parts)}</b> part = <b>${fmt(ins / parts)}</b> kali per part (teori 1.25).
         Lihat ${T_("number_in", "Number In")} di bagian Process.</li>
         <li>Utilization Inspektor <b>${pctTxt(util(r, "Inspektor") || 0)}</b> (teori 67%), Teknisi <b>${pctTxt(util(r, "Teknisi") || 0)}</b> (teori 38%).</li></ul>
         Saat animasi, angka kecil di cabang True/False Decide menunjukkan berapa entity yang lewat tiap cabang.`; }},
    {title: "10. Decide berdasarkan kondisi", target: "#side",
     enter: st => { st.before = lastResults; },
     body: () => `Sekarang aturannya diubah: part boleh diperbaiki paling banyak <b>sekali</b>. Kita pakai kondisi pada ${T_("attribute", "attribute")}.
       <ol><li>Klik <b>■ End</b>. Tambahkan <b>Assign</b> di antara <b>Perbaikan</b> dan <b>Inspeksi</b>: hapus garis Perbaikan → Inspeksi (klik garisnya, tekan Delete), lalu sambungkan Perbaikan → Assign → Inspeksi.
         Di Assign, isi Type <b>Attribute</b>, Attribute Name <code>Sudah Diperbaiki</code>, New Value <code>1</code>.</li>
       <li>Tambahkan Decide kedua bernama <code>Boleh Diperbaiki?</code> di cabang False Decide <b>Lulus?</b>: Type <b>2-way by Condition</b>, If <b>Expression</b>, Value <code>Sudah Diperbaiki == 0</code>.
         True → Perbaikan, False → Dispose baru <code>Part Ditolak</code>.</li>
       <li>Jalankan lagi.</li></ol>`,
     need: st => { const a = nodesOf("assign").find(n => (n.props.assignments || []).some(x => x.type === "Attribute" && norm(x.attribute) === "sudah diperbaiki" && +x.value === 1));
       const d = named("decide", "Boleh Diperbaiki?"), rep = named("process", "Perbaikan"), ins = named("process", "Inspeksi"), rej = named("dispose", "Part Ditolak");
       return [[!!a, "Assign: Attribute Sudah Diperbaiki = 1"], [linkTo(rep, a) && linkTo(a, ins), "Perbaikan → Assign → Inspeksi"],
         [!!d && d.props.type === "2-way by Condition" && /sudah\s*diperbaiki\s*==?\s*0/i.test(String(d.props.value || "")), "Decide 'Boleh Diperbaiki?': 2-way by Condition, Sudah Diperbaiki == 0"],
         [linkTo(named("decide", "Lulus?"), d, "false") && linkTo(d, rep, "true") && linkTo(d, rej, "false"), "Lulus? (False) → Boleh Diperbaiki? → True: Perbaikan, False: Part Ditolak"],
         [!!lastResults && lastResults !== st.before && JSON.stringify(lastResults._model.nodes).includes("Boleh Diperbaiki?"), "Jalankan lagi sampai hasil keluar"]]; }},
    {title: "11. Bandingkan",
     body: st => { const a = st.res1, b = lastResults, per = r => resAvg(r, x => x.counters["Inspeksi.NumberIn"]) / resAvg(r, x => x.entities.in_.Part),
         rp = r => resAvg(r, x => x.counters["Perbaikan.NumberIn"]) / resAvg(r, x => x.entities.in_.Part);
       return `<table class="res"><tr><th></th><th>rework tanpa batas</th><th>maks. 1 kali</th></tr>
         <tr><td>Inspeksi per part</td><td>${fmt(per(a))}</td><td>${fmt(per(b))}</td></tr>
         <tr><td>Utilization Inspektor</td><td>${pctTxt(util(a, "Inspektor") || 0)}</td><td>${pctTxt(util(b, "Inspektor") || 0)}</td></tr>
         <tr><td>Perbaikan per part</td><td>${fmt(rp(a))}</td><td>${fmt(rp(b))}</td></tr></table>
         Teori: perbaikan per part turun dari 0.2 / 0.8 = 0.25 menjadi <b>0.2</b>, inspeksi per part menjadi 1 + 0.2 = <b>1.2</b>, dan sekitar 0.2 × 0.2 = <b>4%</b> part akhirnya ditolak.
         <br>Pelajarannya: <b>2-way by Chance</b> untuk peluang, sedangkan <b>by Condition</b> untuk aturan yang bergantung pada keadaan entity (atribut) atau sistem (misalnya <code>NQ(Inspeksi.Queue) &gt; 5</code>).`; }},
  ]},

  // ---------------------------------------------------------------- 3. Assign
  assign: {title: "Assign: attribute & variable", level: "Dasar", desc: "Mencatat waktu datang, jenis pasien acak, penghitung global, waktu layanan yang bergantung atribut, Record Time Interval.", steps: [
    newStep("Assign: data pada pasien", `Di klinik, setiap pasien membawa datanya sendiri: <b>kapan datang</b> dan <b>jenis</b> pasien (biasa atau kompleks).
      Dengan ${T_("mod_assign", "Assign")} kita memberi nilai ke ${T_("attribute", "attribute")} (milik tiap entity) dan ${T_("variable", "variable")} (satu untuk seluruh model).`),
    createStep("1. Pasien datang", "Pasien", 8, `Beri Name <code>Pasien Datang</code>.`),
    placeStep("2. Modul Assign", "assign", "Data Pasien", "Pasien Datang", "out",
      `Assign memberi nilai tanpa memakan waktu: entity lewat seketika.`),
    {title: "3. Attribute: waktu datang", target: "#side",
     body: () => `Klik <b>Data Pasien</b>. Di baris Assignments pertama, isi:
       <ul><li>Type: <b>Attribute</b></li><li>Attribute Name: <code>Waktu Datang</code></li><li>New Value: <code>TNOW</code></li></ul>
       ${T_("tnow", "TNOW")} adalah jam simulasi saat ini. Setiap pasien menyimpan jam kedatangannya sendiri.`,
     need: () => { const a = named("assign", "Data Pasien"), r = a && a.props.assignments || [];
       return [[r.some(x => x.type === "Attribute" && norm(x.attribute) === "waktu datang" && norm(x.value) === "tnow"), "Attribute Waktu Datang = TNOW"]]; }},
    {title: "4. Attribute: jenis pasien (acak)", target: "#side",
     body: () => `Klik <b>+ Add assignment</b> dan isi Type <b>Attribute</b>, Attribute Name <code>Jenis</code>, New Value <code>DISC(0.7, 1, 1.0, 2)</code>.
       <br>${T_("fn_dist", "DISC")} memakai peluang <b>kumulatif</b>: 70% pasien mendapat Jenis 1 (biasa) dan sisanya (sampai 1.0) Jenis 2 (kompleks).`,
     need: () => { const r = (named("assign", "Data Pasien") || {props: {}}).props.assignments || [];
       return [[r.some(x => x.type === "Attribute" && norm(x.attribute) === "jenis" && /disc\(\s*0?\.7\s*,\s*1\s*,\s*1(\.0)?\s*,\s*2\s*\)/i.test(String(x.value))), "Attribute Jenis = DISC(0.7, 1, 1.0, 2)"]]; }},
    {title: "5. Variable: penghitung global", target: "#side",
     body: () => `Tambah satu assignment lagi: Type <b>Variable</b>, Variable Name <code>Jumlah Pasien</code>, New Value <code>Jumlah Pasien + 1</code>.
       <br>Bedanya: <b>Waktu Datang</b> dan <b>Jenis</b> berbeda untuk setiap pasien, sedangkan <b>Jumlah Pasien</b> hanya ada satu dan dinaikkan oleh setiap pasien yang lewat.`,
     need: () => { const r = (named("assign", "Data Pasien") || {props: {}}).props.assignments || [];
       return [[r.some(x => x.type === "Variable" && norm(x.variable) === "jumlah pasien" && /jumlah pasien\s*\+\s*1/i.test(String(x.value))), "Variable Jumlah Pasien = Jumlah Pasien + 1"]]; }},
    placeStep("6. Pemeriksaan yang bergantung jenis", "process", "Pemeriksaan", "Data Pasien", "out",
      `Isi Resource <code>Dokter</code>, Delay Type <b>Expression</b>, Expression <code>TRIA(3, 4, 6) * Jenis</code>, Units <b>Minutes</b>. Pasien kompleks (Jenis 2) diperiksa dua kali lebih lama: attribute dipakai di dalam rumus.`, p => [
      [usesRes(p, "Dokter"), "Resources: Resource Name = Dokter"],
      [!!p && p.props.delay_type === "Expression" && /tria\(\s*3\s*,\s*4\s*,\s*6\s*\)\s*\*\s*jenis/i.test(String(p.props.expression)) && p.props.units === "Minutes", "Delay Expression TRIA(3, 4, 6) * Jenis, Minutes"]]),
    placeStep("7. Record: lama di klinik", "record", "Lama di Klinik", "Pemeriksaan", "out",
      `Isi Type <b>Time Interval</b>, Attribute Name <code>Waktu Datang</code>. ${T_("mod_record", "Record")} mencatat <code>TNOW − Waktu Datang</code>, yaitu lama pasien di klinik, ke tally bernama "Lama di Klinik".`, r => [
      [!!r && r.props.type === "Time Interval" && norm(r.props.attribute) === "waktu datang", "Type Time Interval, Attribute Name Waktu Datang"]]),
    placeStep("8. Pasien pulang", "dispose", "Pasien Pulang", "Lama di Klinik", "out"),
    {title: "9. Laporkan variable", target: '.pal.data[data-table="variables"]',
     body: () => `Klik <b>Variable</b> di Data modules. Baris <b>Jumlah Pasien</b> sudah dibuat otomatis. Centang <b>Report Statistics</b> supaya nilainya muncul di laporan User Specified.`,
     need: () => [[!!(model.data.variables["Jumlah Pasien"] || {}).report, "Variable Jumlah Pasien: Report Statistics dicentang"]]},
    runStep("10. Jalankan", 5, 8),
    {title: "11. Baca hasilnya", target: "#sum-learn",
     body: () => { const r = lastResults, tl = resAvg(r, x => x.tallies["Lama di Klinik"].average), tt = resAvg(r, x => x.tallies["Pasien.TotalTime"].average);
       const jp = resAvg(r, x => x.dstats["Jumlah Pasien"].final), nin = resAvg(r, x => x.entities.in_.Pasien), ut = util(r, "Dokter");
       return `<ul><li>Tally <b>Lama di Klinik</b> = <b>${fmt(tl)}</b> menit, sama dengan ${T_("total_time", "Total Time")} entity Pasien (${fmt(tt)}), karena keduanya mengukur hal yang sama: dari Create sampai Dispose.</li>
         <li>Nilai akhir <b>Jumlah Pasien</b> = ${fmt(jp)}, sama dengan Number In Pasien (${fmt(nin)}).</li>
         <li>Utilization Dokter ${pctTxt(ut || 0)}. Teori: waktu periksa rata-rata = 4.33 × (0.7 × 1 + 0.3 × 2) = 5.63 menit, dibagi selang kedatangan 8 menit = <b>70%</b>.</li></ul>
         Record Time Interval berguna untuk mengukur <b>bagian</b> dari alur, misalnya hanya dari pendaftaran sampai selesai diperiksa: letakkan Assign dan Record di titik yang Anda mau.`; }},
  ]},

  // ---------------------------------------------------------------- 4. Schedule
  schedule: {title: "Schedule: jam sibuk & shift", level: "Menengah", desc: "Laju kedatangan yang berubah per jam, kapasitas teller per jam, Scheduled vs Instantaneous Utilization.", steps: [
    newStep("Schedule: bank dengan jam sibuk", `Bank buka 8 jam. Jam 10–14 (jam ke-3 sampai ke-6) jauh lebih ramai, jadi bank menambah teller hanya pada jam itu.
      Kita memakai dua ${T_("schedule", "Schedule")}: satu untuk <b>laju kedatangan</b> dan satu untuk <b>jumlah teller</b>.`),
    {title: "1. Create mengikuti jadwal", target: '.pal[data-kind="create"]',
     body: () => `Letakkan <b>Create</b> dan isi Name <code>Nasabah Datang</code>, Entity Type <code>Nasabah</code>, Type <b>Schedule</b>, Schedule Name <code>Pola Kedatangan</code>.
       <br>Dengan Type Schedule, laju kedatangan (entity per jam) dibaca dari jadwal. Kedatangannya tetap acak, tetapi rata-ratanya berubah sepanjang hari.`,
     need: () => { const c = nodesOf("create")[0];
       return [[!!c && c.props.type === "Schedule", "Create Type = Schedule"], [!!c && norm(c.props.schedule) === "pola kedatangan", "Schedule Name = Pola Kedatangan"]]; }},
    {title: "2. Isi jadwal kedatangan", target: '.pal.data[data-table="schedules"]',
     body: () => `Klik <b>Schedule</b> di Data modules. Pada baris <b>Pola Kedatangan</b> (Type <b>Arrival</b>), klik <b>📊</b> untuk membuka editor grafis. Isi per jam:
       <ul><li>jam 1–2: <code>12</code> nasabah/jam</li><li>jam 3–6: <code>30</code> nasabah/jam</li><li>jam 7–8: <code>12</code> nasabah/jam</li></ul>
       Caranya: klik atau seret di grafik pada tinggi yang diinginkan. Cara cepat dengan kotak isian di bawah grafik: hilangkan centang <i>other hours = 0</i>, isi <code>00:00</code> sampai <code>08:00</code> nilai 12 lalu klik <b>Fill</b>, kemudian <code>02:00</code> sampai <code>06:00</code> nilai 30 lalu klik <b>Fill</b>. Lalu klik OK.
       Cara lain: klik tombol baris Durations dan isi Value/Duration: 12 for 2, 30 for 4, 12 for 2 (Time Units Hours).`,
     need: () => { const sc = model.data.schedules["Pola Kedatangan"];
       return [[!!sc && sc.type === "Arrival", "Schedule Pola Kedatangan bertipe Arrival"], [hourly(sc, 8) === "12,12,30,30,30,30,12,12", "Per jam: 12, 12, 30, 30, 30, 30, 12, 12"]]; }},
    placeStep("3. Layanan teller", "process", "Layanan Teller", "Nasabah Datang", "out", `Isi Resource <code>Teller</code>, Delay Triangular <code>2 / 3 / 4</code> Minutes.`, p => [
      [usesRes(p, "Teller"), "Resources: Resource Name = Teller"], [tria(p, 2, 3, 4), "Triangular 2 / 3 / 4 Minutes"]]),
    placeStep("4. Nasabah pulang", "dispose", "Nasabah Pulang", "Layanan Teller", "out"),
    {title: "5. Teller mengikuti shift", target: '.pal.data[data-table="resources"]',
     body: () => `Klik <b>Resource</b> di Data modules. Pada baris <b>Teller</b>, ubah Type menjadi <b>Based on Schedule</b>, Schedule Name <code>Shift Teller</code>.
       <br><b>Schedule Rule</b> menentukan apa yang terjadi kalau kapasitas turun saat teller sedang melayani:
       <ul><li><b>Wait</b>: teller menyelesaikan nasabahnya dulu, lalu periode berikutnya bergeser.</li><li><b>Ignore</b>: kapasitas turun saat itu juga, tetapi nasabah yang sedang dilayani tetap diselesaikan.</li><li><b>Preempt</b>: layanan dihentikan dan dilanjutkan nanti.</li></ul>`,
     need: () => { const r = model.data.resources.Teller;
       return [[!!r && r.type === "Based on Schedule", "Teller: Type Based on Schedule"], [!!r && norm(r.schedule) === "shift teller", "Schedule Name = Shift Teller"]]; }},
    {title: "6. Isi jadwal shift", target: '.pal.data[data-table="schedules"]',
     body: () => `Buka lagi <b>Schedule</b>. Baris <b>Shift Teller</b> (Type <b>Capacity</b>) sudah dibuat otomatis. Isi per jam:
       <ul><li>jam 1–2: <code>1</code> teller</li><li>jam 3–6: <code>3</code> teller</li><li>jam 7–8: <code>1</code> teller</li></ul>`,
     need: () => { const sc = model.data.schedules["Shift Teller"];
       return [[!!sc && sc.type === "Capacity", "Schedule Shift Teller bertipe Capacity"], [hourly(sc, 8) === "1,1,3,3,3,3,1,1", "Per jam: 1, 1, 3, 3, 3, 3, 1, 1"]]; }},
    {title: "7. Hitung dulu",
     body: () => `Beban per teller (${T_("rho", "ρ")}) = kedatangan per jam × 3 menit ÷ 60 ÷ jumlah teller:
       <ul><li>jam sepi: 12 × 3 / 60 / 1 = <b>60%</b></li><li>jam sibuk: 30 × 3 / 60 / 3 = <b>50%</b></li></ul>
       Rata-rata teller tersedia = (1×2 + 3×4 + 1×2) / 8 = <b>2</b>. Jumlah nasabah sehari ≈ 12×2 + 30×4 + 12×2 = <b>168</b>.`},
    runStep("8. Jalankan", 5, 8),
    {title: "9. Baca hasilnya", target: "#sum-learn",
     enter: st => { st.res1 = lastResults; },
     body: st => { const r = st.res1, x = k => resAvg(r, y => y.resources.Teller[k]);
       return `<ul><li>${T_("number_sched", "Number Scheduled")} = <b>${fmt(x("number_scheduled"))}</b> (teori 2). ${T_("number_busy", "Number Busy")} = ${fmt(x("number_busy"))}.</li>
         <li>${T_("inst_util", "Instantaneous Utilization")} = <b>${pctTxt(x("instantaneous_utilization") || 0)}</b>, yaitu rata-rata terhadap waktu dari (sibuk ÷ tersedia) pada setiap saat.</li>
         <li>${T_("sched_util", "Scheduled Utilization")} = <b>${pctTxt(x("scheduled_utilization") || 0)}</b> = Number Busy ÷ Number Scheduled. Untuk kapasitas yang berubah, kedua angka ini bisa berbeda.</li>
         <li>Nasabah dilayani: <b>${fmt(resAvg(r, y => y.entities.out.Nasabah))}</b> per hari (teori ≈ 168). Rata-rata menunggu ${fmt(qWait(r, "Layanan Teller.Queue"))} menit.</li></ul>`; }},
    {title: "10. Eksperimen: hanya 2 teller saat jam sibuk", target: '.pal.data[data-table="schedules"]',
     enter: st => { st.before = lastResults; },
     body: () => `Klik <b>■ End</b>, ubah Shift Teller pada jam 3–6 dari 3 menjadi <code>2</code>, lalu jalankan lagi. Beban jam sibuk menjadi 30 × 3 / 60 / 2 = <b>75%</b>.`,
     need: st => { const sc = model.data.schedules["Shift Teller"];
       return [[hourly(sc, 8) === "1,1,2,2,2,2,1,1", "Shift Teller per jam: 1, 1, 2, 2, 2, 2, 1, 1"],
         [!!lastResults && lastResults !== st.before && hourly(lastResults._model.data.schedules["Shift Teller"], 8) === "1,1,2,2,2,2,1,1", "Jalankan lagi"]]; }},
    {title: "11. Bandingkan",
     body: st => { const a = st.res1, b = lastResults, x = (r, k) => resAvg(r, y => y.resources.Teller[k]);
       return `<table class="res"><tr><th></th><th>3 teller sibuk</th><th>2 teller sibuk</th></tr>
         <tr><td>Number Scheduled</td><td>${fmt(x(a, "number_scheduled"))}</td><td>${fmt(x(b, "number_scheduled"))}</td></tr>
         <tr><td>Scheduled Utilization</td><td>${pctTxt(x(a, "scheduled_utilization") || 0)}</td><td>${pctTxt(x(b, "scheduled_utilization") || 0)}</td></tr>
         <tr><td>Waiting Time (menit)</td><td>${fmt(qWait(a, "Layanan Teller.Queue"))}</td><td>${fmt(qWait(b, "Layanan Teller.Queue"))}</td></tr></table>
         Mengurangi 4 jam-teller menghemat biaya, tetapi waktu tunggu naik. Dengan Schedule, Anda bisa mencari susunan shift yang paling hemat namun waktu tunggunya masih dapat diterima.`; }},
  ]},
};
const DONE_STEP = {title: "Selesai 🎉", body: () => `Tutorial selesai.
  <ul><li>Simpan model dengan <b>File → Save</b> (Ctrl+S), atau <b>File → Export JSON</b> untuk mengunduh file.</li>
  <li>Tekan <kbd>F1</kbd> atau tombol <b>?</b> di kanan atas untuk daftar istilah.</li>
  <li>Pilih tutorial lain lewat tombol 🎓, atau buka contoh dari buku: <b>File → Open… → Altiok 5-2 / 5-6 / 5-7</b>.</li></ul>`};
for (const t of Object.values(TOURS)) t.steps.push(DONE_STEP);

const tourEl = document.createElement("section");
tourEl.id = "tour"; tourEl.hidden = true; tourEl.setAttribute("aria-live", "polite"); tourEl.setAttribute("aria-label", "Tutorial");
document.body.appendChild(tourEl);
let tour = null;
const doneTours = () => { try { return JSON.parse(localStorage.getItem("simcore.tours") || "{}"); } catch (e) { return {}; } };
function startTour(key) {
  tourEl.removeAttribute("style");
  if (!key || !TOURS[key]) return tourMenu();
  tour = {key, i: 0, st: {}}; showStep();
}
function tourMenu() {
  tour = null; tourEl.hidden = false;
  const done = doneTours();
  tourEl.innerHTML = `<div class="tourhead"><span class="hint">Tutorial terpandu</span><span style="flex:1"></span><button id="tourx" title="Tutup">✕</button></div>
    <h3>Pilih tutorial</h3><div class="tourmenu">${Object.entries(TOURS).map(([k, t]) =>
      `<button data-tour="${k}"><b>${done[k] ? "✅ " : ""}${t.title}</b><span class="hint">${t.level} · ${t.steps.length - 1} langkah · ${t.desc}</span></button>`).join("")}</div>`;
  $("tourx").onclick = endTour;
  for (const b of tourEl.querySelectorAll("[data-tour]")) b.onclick = () => startTour(b.dataset.tour);
}
function endTour() { tour = null; tourEl.hidden = true; document.querySelectorAll(".tut-hl").forEach(e => e.classList.remove("tut-hl")); }
function showStep() {
  const steps = TOURS[tour.key].steps, s = steps[tour.i];
  if (s.enter && !tour.st["entered" + tour.i]) { tour.st["entered" + tour.i] = true; s.enter(tour.st); }
  if (s.target && s.target.startsWith(".pal")) {   // make sure the tile is visible
    const b = document.querySelector(s.target), body = b && b.closest(".pbbody"); if (body && body.hidden) body.previousElementSibling.click();
  }
  const tgt = s.target && document.querySelector(s.target);
  if (tgt && tgt.closest("#panes")) tgt.scrollIntoView({block: "start", behavior: "smooth"});
  const last = tour.i === steps.length - 1;
  if (last) { const d = doneTours(); d[tour.key] = true; try { localStorage.setItem("simcore.tours", JSON.stringify(d)); } catch (e) {} }
  tourEl.hidden = false;
  let body; try { body = s.body(tour.st); } catch (e) { body = "<p class='hint'>(Hasil sebelumnya tidak tersedia; jalankan lagi.)</p>"; }
  tourEl.innerHTML = `<div class="tourhead"><span class="hint">${esc(TOURS[tour.key].title)} · langkah ${tour.i + 1} dari ${steps.length}</span><span style="flex:1"></span><button id="tourx" title="Tutup tutorial">✕</button></div>
    <h3>${s.title}</h3><div class="tourbody">${body}</div>
    <div class="tourstate" id="tourstate"></div>
    <div class="dlgbtns"><button id="tourmenu">☰ Tutorial lain</button><span style="flex:1"></span><button id="tourback" ${tour.i ? "" : "disabled"}>‹ Kembali</button><button id="tournext" class="primary">${s.start || (last ? "Tutup" : NEXT_OK)}</button></div>`;
  $("tourx").onclick = endTour;
  $("tourmenu").onclick = tourMenu;
  $("tourback").onclick = () => { tour.i--; showStep(); };
  $("tournext").onclick = () => {
    if (s.onStart) s.onStart();
    if (last) return endTour();
    tour.i++; showStep();
  };
  checkStep();
}
// the card sits at the bottom-left of the canvas, at the bottom-right over the results, or top-right of the canvas while the spreadsheet is open;
// dragging its title bar puts it where the student wants it
tourEl.addEventListener("pointerdown", ev => {
  if (!ev.target.closest(".tourhead") || ev.target.closest("button")) return;
  const r = tourEl.getBoundingClientRect(), dx = ev.clientX - r.left, dy = ev.clientY - r.top;
  tourEl.dataset.moved = "1"; tourEl.classList.remove("up");
  const move = e => { tourEl.style.left = Math.max(0, e.clientX - dx) + "px"; tourEl.style.top = Math.max(0, e.clientY - dy) + "px"; tourEl.style.right = tourEl.style.bottom = "auto"; };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
  addEventListener("pointermove", move); addEventListener("pointerup", up);
});
function checkStep() {
  if (tourEl.hidden) return;
  if (!tourEl.style.left) {   // keep clear of what the student is working on
    const open = $("bottom").classList.contains("open"), sheetOn = open && $("p-sheet").classList.contains("on");
    tourEl.classList.toggle("up", open && !sheetOn); tourEl.classList.toggle("top", sheetOn);
  }
  if (!tour) return;
  const s = TOURS[tour.key].steps[tour.i];
  document.querySelectorAll(".tut-hl").forEach(e => e.classList.remove("tut-hl"));
  let needs = [];
  try { needs = s.need ? s.need(tour.st) : []; } catch (e) { needs = [[false, "…"]]; }
  const missing = needs.filter(n => !n[0]), ok = !missing.length;
  const t = s.target && document.querySelector(s.target);
  if (t && (!ok || !s.need)) t.classList.add("tut-hl");
  const st = $("tourstate");
  if (!st || !s.need) return;
  const html = ok ? "✅ Bagus! Klik <b>Lanjut</b>." : `⏳ Belum:<ul>${missing.map(m => `<li>${esc(m[1])}</li>`).join("")}</ul>`;
  if (st.innerHTML !== html) st.innerHTML = html;
  st.className = "tourstate" + (ok ? " ok" : "");
  $("tournext").disabled = !ok;
  if (ok && !tour.st["auto" + tour.i]) { tour.st["auto" + tour.i] = true; $("tournext").focus({preventScroll: true}); }
}
setInterval(checkStep, 400);
