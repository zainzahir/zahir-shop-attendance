 ZAHIR SHOP — DIGITAL ATTENDANCE SYSTEM
======================================================================
DESKTOP CLIENT SETUP & INSTALLATION GUIDE
======================================================================

This guide explains how to install, configure, and run the biometric attendance 
desktop application on your client's Windows PC.

----------------------------------------------------------------------
PREREQUISITES
----------------------------------------------------------------------
1. Operating System: Windows 10 or Windows 11 (64-bit).
2. Hardware: Suprema BioMini Slim 2 fingerprint scanner.
3. Network: Stable internet connection (required to sync attendance logs 
   to the Supabase cloud database).
4. System Packages: Microsoft Visual C++ 2015-2022 Redistributable (x64)
   must be installed. (Download from Microsoft if missing).

----------------------------------------------------------------------
STEP 1: INSTALL SCANNER DRIVERS
----------------------------------------------------------------------
Before launching the application, you must ensure that Windows recognizes 
the fingerprint scanner:

1. Plug the Suprema BioMini Slim 2 scanner into a USB port.
2. In most cases, Windows 10/11 will automatically download and install the 
   correct driver via Windows Update within a few seconds. The scanner's 
   sensor window should light up briefly.
3. To verify:
   - Open 'Device Manager' on Windows (search for it in the Start Menu).
   - Look for a section named "Biometric Devices".
   - You should see "Suprema Fingerprint Scanner" or "Suprema BioMini Slim 2" 
     listed without any warning triangles.
4. If Windows does not install the driver automatically:
   - Download the official driver installer from the Suprema Support website:
     https://support.supremainc.com/
   - Under the downloads section, search for "BioMini Slim 2 Driver" or 
     "Suprema USB Driver Installer". Run the installer and restart your PC.

----------------------------------------------------------------------
STEP 2: CONFIGURE THE DATABASE CONNECTION (.env)
----------------------------------------------------------------------
The app connects directly to your Supabase PostgreSQL cloud database. You must 
fill in the connection string inside the config file:

1. Inside the application folder, find the file named `.env`.
2. Open it in Notepad or any text editor.
3. You will see a line like:
   DATABASE_URL=postgresql://postgres.xxx...
4. Replace this connection URL with your actual Supabase database connection 
   string (obtainable from Supabase Dashboard -> Project Settings -> Database).
5. Save and close the file.

----------------------------------------------------------------------
STEP 3: LAUNCH THE APPLICATION
----------------------------------------------------------------------
1. Double-click the main executable:
   ZahirAttendance.exe
2. The application window will open.
3. If the scanner is correctly connected, you will see status messages in the 
   terminal/log section.
4. If the scanner is not connected, the app will show an error message. Plug in 
   the scanner and restart the app.

----------------------------------------------------------------------
HOW TO USE THE APP
----------------------------------------------------------------------
- Tab 1: ENROLLMENT (Register Employees)
  1. Fill in the employee's Full Name, CNIC, Phone, and Address.
  2. Click "Enroll Fingerprint".
  3. The scanner window will light up. Place the employee's thumb/finger 
     flatly on the scanner twice when prompted.
  4. The employee profile and their biometric template are securely saved to the database.

- Tab 2: ATTENDANCE (Daily Log in/out)
  1. Click "Start Attendance Loop".
  2. The scanner will remain active.
  3. Employees simply place their thumb on the scanner.
  4. The system automatically identifies them, plays a chime (success or error), 
     computes if they are Present/Late based on your shop's shift settings, 
     and uploads the log to the cloud in real-time.

----------------------------------------------------------------------
TROUBLESHOOTING
----------------------------------------------------------------------
- Error: "Unable to load DLL..." or "Module not found"
  -> Make sure all DLL files (BS_SDK_V2.dll, UFScanner.dll, etc.) are in the 
     same folder as the executable or the _internal directory.
  -> Install the Visual C++ Redistributable (x64) from Microsoft.

- Scanner is connected but does not light up / scan:
  -> Check the USB connection or try a different USB port.
  -> Open Device Manager to check if the driver is installed.

- Error connecting to database:
  -> Check your internet connection.
  -> Verify that the connection string in `.env` is 100% correct and matches 
     your Supabase URI.
