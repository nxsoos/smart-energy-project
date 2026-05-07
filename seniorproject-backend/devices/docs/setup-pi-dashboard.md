# Raspberry Pi Dashboard Setup

The local dashboard runs on the Raspberry Pi at:

```text
http://localhost:5001
```

From another device on the same Wi-Fi:

```text
http://10.220.38.94:5001
```

If the Pi is using a phone hotspot, the IP address may change. Check it on the
Pi with:

```bash
hostname -I
```

## Copy Updated Dashboard Files From Windows CMD

Run these from Windows CMD:

```cmd
scp "C:\Nasser\smart-energy-project\seniorproject-backend\devices\dashboard_server.py" ali@10.220.38.94:/home/ali/smart-energy-hub/
scp -r "C:\Nasser\smart-energy-project\seniorproject-backend\devices\templates" ali@10.220.38.94:/home/ali/smart-energy-hub/
scp -r "C:\Nasser\smart-energy-project\seniorproject-backend\devices\static" ali@10.220.38.94:/home/ali/smart-energy-hub/
scp "C:\Nasser\smart-energy-project\seniorproject-backend\devices\main.py" ali@10.220.38.94:/home/ali/smart-energy-hub/
scp "C:\Nasser\smart-energy-project\seniorproject-backend\devices\requirements-ai.txt" ali@10.220.38.94:/home/ali/smart-energy-hub/
```

## Update The Pi Service

Run these on the Pi:

```bash
cd /home/ali/smart-energy-hub
source venv/bin/activate
pip install -r requirements-ai.txt
sudo systemctl restart smart-energy-hub.service
sudo systemctl status smart-energy-hub.service
journalctl -u smart-energy-hub.service -f
```

The main service should start:

```text
firebase_tuya_cloud_controller.py
esp32_sensor_receiver.py
dashboard_server.py
```

## Test The Dashboard

On the Pi screen:

```text
http://localhost:5001
```

From a laptop or phone on the same Wi-Fi:

```text
http://10.220.38.94:5001
```

Test the API:

```bash
curl http://localhost:5001/api/latest
```

## Breaker Commands

The dashboard writes breaker commands to the same path watched by
`firebase_tuya_cloud_controller.py`:

```text
homes/home_001/commands/{device_id}/latest
```

It also mirrors the command at:

```text
homes/home_001/commands/{cmd_id}
```

## Kiosk Mode On Raspberry Pi Boot

Create the autostart folder if it does not exist:

```bash
mkdir -p ~/.config/lxsession/LXDE-pi
```

Edit the autostart file:

```bash
nano ~/.config/lxsession/LXDE-pi/autostart
```

Add or update these lines:

```text
@xset s off
@xset -dpms
@xset s noblank
@chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:5001
```

Reboot the Pi:

```bash
sudo reboot
```

After boot, Chromium should open the local dashboard automatically.
