# smx — Linux için SMX-R22 fare kontrolü

**SMX-R22** oyun faresini (USB kimliği `30fa:1040`, "INSTANT USB GAMING MOUSE" olarak görünür)
Linux'ta ayarlamak için terminal uygulaması. Windows yazılımına gerek yok. Arayüz Türkçe ve
İngilizce; dil ilk açılışta otomatik algılanır.

[English README](README.md)

## Özellikler

| | |
|---|---|
| DPI | 6 kademe (200–12800), kademeyi açma/kapama, aktif kademe, alttaki ışık şeridinin kademe rengi (üstteki DPI göstergesinin renkleri fareye sabit) |
| Tuşlar | 7 tuş: sol/sağ/orta tık, geri/ileri, DPI döngüsü/±, çift tık, hızlı ateş, masaüstünü göster, LED döngüsü, devre dışı |
| Kısayollar | 40'tan fazla hazır kısayol (kilitle, pencere görünümü, ekran görüntüsü, kopyala/yapıştır, sekme işlemleri, ses…) ve özel kısayol oluşturucu |
| Işık | 14 LED efekti, hız, parlaklık |
| Canlı | Değişiklikler anında fareye yazılır; aktif DPI kademesi fareyi takip eder; basılan tuşlar çizimde yanar |
| Güvenli | Açılışta otomatik yedek, geri okuyarak doğrulama, USB kimlik başlığına asla yazılmaz |

Henüz yok: çok adımlı makrolar. Polling rate bu modelde değiştirilemiyor (resmî yazılım da
desteklemiyor). Medya tuşları (oynat/duraklat, sonraki/önceki) deneysel.

## Kurulum

```sh
git clone https://github.com/emreatmaca0/smx-r22-linux.git && cd smx-r22-linux
sudo cp 70-smx-r22.rules /etc/udev/rules.d/ && sudo udevadm control --reload
# fareyi çıkarıp tak
ln -sf "$PWD/smx" ~/.local/bin/smx
```

## Kullanım

`smx` yaz. Sadece dört tuş var: `↑↓` seç, `←→` değiştir (anında fareye uygulanır),
`Enter` renk seçici / liste, `q` çık.

- DPI kademesini kapatmak için değeri 200'ün altına (ya da 12800'ün üstüne) götür.
- Tuş satırında `Enter`: temel işlevler, sistem, düzenleme, tarayıcı, medya ve "özel kısayol
  oluştur" listesi.
- Kademe satırında `Enter`: renk seçici. Ekrandaki renkler fareyle uyuşmazsa
  *Diğer › LED renk düzeni* ayarını değiştir.
- Fare çizimi terminal en az 100 sütun genişliğindeyse görünür.

Komut satırı: `smx status`, `smx backup`, `smx restore DOSYA`, `smx dpi 5 3200`,
`smx dump 0x00 0x40`, `smx listen`, `smx tui --demo DOSYA`, `smx --lang tr`.

Güvenlik ve protokol ayrıntıları için [README.md](README.md) ve [PROTOCOL.md](PROTOCOL.md).

## Lisans

MIT — bkz. [LICENSE](LICENSE).
