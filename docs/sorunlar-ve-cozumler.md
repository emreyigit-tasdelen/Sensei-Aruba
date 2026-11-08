
# Sensei-Aruba - Sorunlar ve Çözümler

| Problem | Neden (kök neden) | Çözüm | Tekrarını önleme |
|---|---|---|---|
| Anahtar ekli ama SSH reddediyor | PC'deki ana anahtar passphrase'li; otomasyon passphrase giremez | Sadece bu sunucu için passphrase'siz ayrı anahtar | Otomasyona ayrı anahtar |
| Yeni anahtar da çalışmıyor | PowerShell'de `ssh-keygen -N '""'` boş değil `""` passphrase üretir | `ssh-keygen -p -P '""' -N ''` | PowerShell'de `-N ''` yaz |
| Model çalışırken SSH kopuyor | Ollama tüm CPU'yu alıyor, VM dizüstüyle CPU paylaşıyor | Ollama `cpus: 10`, docling/rag-api `cpus: 4` | Her servise CPU sınırı |
| `scp` → Permission denied | `sources` klasörünü Docker root sahipliğinde oluşturdu | `sudo chown -R $USER:$USER sources` | Klasörleri compose'dan önce aç |
| İndeks hazır değilken "bulunamadı" + Hakem RED | Boş bağlamla cevap üretildi | İki aşamalı indeksleme (önce anahtar kelime), boş bağlamda hakem çalışmaz | — |
| VMC modeli listede yok | İndeksleme sıralıydı, VMC 6200M'i bekliyordu | Önce tüm cihazların anahtar kelime indeksi, sonra vektörler | — |
| "802.1x" bulunamıyor | Kullanıcı terimi ≠ CLI terimi (`dot1x`) | Eşanlamlı sözlüğü (`SYNONYMS`) | Yeni markada sözlüğü genişlet |
| Compose'daki Open WebUI ayarı uygulanmıyor | Ayarlar ilk açılışta veritabanına yazılıyor | `ENABLE_PERSISTENT_CONFIG: false` | — |
| Windows'ta boş RAM 1,1 GB | VMware, VM'in kullandığı belleği geri vermiyor; VM 24 GB'tı | VM 14 GB, model 5 dk sonra boşalır, boşta önbellek bırakılır, AI Uyut | VM'e ihtiyacın kadar RAM ver |
| Uykudan sonra web arayüzü açılmıyor | Docker iç ağı uykudan sonra veri iletmiyor (TCP var, TLS cevapsız) | `wake.sh`: önce konteyner, olmazsa Docker servisi yeniden başlatılır | AI Başlat bunu otomatik yapar (~3 dk) |
| 4111 sayfalık PDF Docling'de bitmez | CPU'da OCR/layout analizi sayfa başına saniyeler | `pdf_to_md.py` (PyMuPDF + yer imleri → başlık) | Büyük metin PDF'lerinde bu aracı kullan |
| markitdown çıktısında kelimeler bitişik | PDF metin katmanında boşluk karakteri yok | PyMuPDF konumdan boşlukları yeniden kuruyor | Dönüşümden sonra örnek sayfayı kontrol et |
| Doğrulama dosya/parametre adlarını "dizinde yok" diyor | Ters tırnaklı her ifade komut sanılıyordu | Yalnız cihazın komut köküyle başlayanlar kontrol edilir | — |
| Web arayüzü 502 (Caddy ayakta, Open WebUI sağlıklı) | Sunucudaki Caddyfile `reverse_proxy 127.0.0.1:8080` olarak değiştirilmişti; Caddy kendi konteynerinde olduğu için 127.0.0.1 kendisi | Repodaki Caddyfile (`open-webui:8080`) gönderildi, caddy yeniden başlatıldı | Sunucuda dosyayı elle değiştirme; değişikliği repoda yap, sonra kopyala. Caddy logunda `dial tcp 127.0.0.1:8080` görürsen bu |
| Bash'ten `ssh aruba-bot` çözülmüyor | Git Bash ssh'i Windows `~/.ssh/config`'i okumuyor | `C:\Windows\System32\OpenSSH\ssh.exe` | — |

## Crawler (CLI ağacı tarama) dersleri

| Problem | Neden (kök neden) | Çözüm | Tekrarını önleme |
|---|---|---|---|
| Tarama 45 bin adımdan sonra bitmiyor (`show ap database ...`) | Filtre/sıralama seçenekleri (`usb`, `indoor`, `status`...) her sırayla art arda yazılabiliyor; DFS her permütasyonu ayrı geziyor | Aynı son kelime + aynı alt seçenek kümesi görüldüyse altına inme (`seen`); algoritma listelerinde (`ssh key-exchange-algorithms`) aynı havuzdan 3. seçime inen dal atlanır (`pooled`) | Yeni markada önce `--depth 5` ile geniş tara; kuyruk düşmüyorsa permütasyon dalı vardır |
| 6200M SSH girişi bir süre reddetti (`Error reading SSH protocol banner`) | ~14 bin `?` sorgusundan sonra cihaz geçici engelledi (kesin neden doğrulanmadı); ping açıktı | Script 20–30 sn'de bir yeniden denedi, engel kalkınca state'ten devam etti | `--wait` ile hızı makul tut; yeniden denemeli çalıştır |
| AOS-CX'te tarama istemi tanınmadı | VMC istemi `(host) [node] #`, CX istemi `host#`; CX'te `enable` yok, sayfalama `no page` | CX kopyasında `PROMPT` regex'i, `no page`, mod adı `exec` | Yeni cihaz = istem regex'ini ve sayfalama komutunu önce elle dene |
| Paralel tarama | Tek oturum saatler sürüyordu | `--root mod:komut` ile dal başına ayrı oturum (3 paralel), `--skip` ile çakışma önlenir | Cihaz oturum limitine dikkat |

> Crawler hiçbir komut çalıştırmaz; yalnız yazıp `?` basar ve satırı siler. Şifre kodda tutulmaz.
