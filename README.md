# PowerSlate
An integration between PowerCampus and Slate (hence the name). Admissions applications are transmitted from PowerCampus to Slate and some data from PowerCampus is transmitted back to Slate.

[Graphical diagram](PowerSlate%20Overview.png)

[Field documentation](PowerSlate%20Integration%20Fields.docx)

## Requirements
Python 3.9+ is required, along with a few packages available via pip. There are no known issues between different package versions.

## Usage
### Configuration
Copy `config_sample.json` to a new file, then edit the values for your environment.

### Timed sync
Execute `sync_ondemand.py` and pass the name of the configuration file as an argument. This can be used with an external task scheduler, such as Task Scheduler in Windows.

Example for Windows PowerShell : `python.exe .\sync_ondemand.py config_sample.json`

### User-Trigged Sync
Execute `sync_http.py` and pass the name of the configuration file as an argument. It will start a webserver on port 8887 that you can link to from within Slate. The link should contain the GUID of the person as the parameter `pid`. Example: `http://server:8887/?pid=84f2060e-5d9d-437b-b5be-9558679edac4`
