import requests
import json
from copy import deepcopy
import xml.etree.ElementTree as ET
from ps_format import format_app_generic, format_app_api,  format_app_sql
import ps_powercampus


def init(config_path):
    """Reads config file to global CONFIG dict. Many frequently-used variables are copied to their own globals for convenince."""
    global CONFIG
    global CONFIG_PATH
    global FIELDS
    global RM_MAPPING
    global MSG_STRINGS

    CONFIG_PATH = config_path
    # Read config file and convert to dict
    with open(CONFIG_PATH) as file:
        CONFIG = json.loads(file.read())

    RM_MAPPING = ps_powercampus.get_recruiter_mapping(
        CONFIG['mapping_file_location'])

    # Init PowerCampus API and SQL connections
    ps_powercampus.init(CONFIG)

    # Misc configs
    MSG_STRINGS = CONFIG['msg_strings']

    return CONFIG


def de_init():
    """Release resources like open SQL connections."""
    ps_powercampus.de_init()


def verbose_print(x):
    """Attempt to print JSON without altering it, serializable objects as JSON, and anything else as default."""
    if CONFIG['console_verbose'] and len(x) > 0:
        if isinstance(x, str):
            print(x)
        else:
            try:
                print(json.dumps(x, indent=4))
            except:
                print(x)


def slate_get_actions(apps_list):
    """Fetch 'Scheduled Actions' (Slate Checklist) for a list of applications.

    Keyword arguments:
    apps_list -- list of ApplicationNumbers to fetch actions for

    Returns:
    action_list -- list of individual action as dicts

    Uses its own HTTP session to reduce overhead and queries Slate with batches of 48 comma-separated ID's.
    48 was chosen to avoid exceeding max GET request.
    """

    # Set up an HTTP session to use for multiple GET requests.
    http_session = requests.Session()
    http_session.auth = (CONFIG['scheduled_actions']['slate_get']['username'],
                         CONFIG['scheduled_actions']['slate_get']['password'])

    actions_list = []

    while apps_list:
        counter = 0
        ql = []  # Queue list
        qs = ''  # Queue string
        al = []  # Temporary actions list

        # Pop up to 48 app GUID's and append to queue list.
        while apps_list and counter < 48:
            ql.append(apps_list.pop())
            counter += 1

        # Stuff them into a comma-separated string.
        qs = ",".join(str(item) for item in ql)

        r = http_session.get(
            CONFIG['scheduled_actions']['slate_get']['url'], params={'aids': qs})
        r.raise_for_status()
        al = json.loads(r.text)
        actions_list.extend(al['row'])
        # if len(al['row']) > 1: # Delete. I don't think an application could ever have zero actions.

    http_session.close()

    return actions_list


def slate_post_generic(upload_list, config_dict):
    """Upload a simple list of dicts to Slate with no transformations."""

    # Slate requires JSON to be convertable to XML
    upload_dict = {'row': upload_list}

    creds = (config_dict['username'], config_dict['password'])
    r = requests.post(config_dict['url'], json=upload_dict, auth=creds)
    r.raise_for_status()


def slate_post_fields_changed(apps, config_dict):
    # Check for changes between Slate and local state
    # Upload changed records back to Slate

    # Build list of flat app dicts with only certain fields included
    upload_list = []
    fields = deepcopy(config_dict['fields_string'])
    fields.extend(config_dict['fields_bool'])
    fields.extend(config_dict['fields_int'])

    if len(fields) == 1:
        return

    for app in apps.values():
        CURRENT_RECORD = app['aid']
        upload_list.append({k: v for (k, v) in app.items() if k in fields
                            and v != app["compare_" + k]} | {'aid': app['aid']})

    # Apps with no changes will only contain {'aid': 'xxx'}
    # Only retain items that have more than one field
    upload_list[:] = [app for app in upload_list if len(app) > 1]

    if len(upload_list) > 0:
        # Slate requires JSON to be convertable to XML
        upload_dict = {'row': upload_list}

        creds = (config_dict['username'], config_dict['password'])
        r = requests.post(config_dict['url'], json=upload_dict, auth=creds)
        r.raise_for_status()

    msg = '\t' + str(len(upload_list)) + ' of ' + \
        str(len(apps)) + ' apps had changed fields'
    return msg


def slate_post_fields(apps, config_dict):
    # Build list of flat app dicts with only certain fields included
    upload_list = []
    fields = ['aid']
    fields.extend(config_dict['fields'])

    for app in apps.values():
        CURRENT_RECORD = app['aid']
        upload_list.append({k: v for (k, v) in app.items()
                            if k in fields})

    # Slate requires JSON to be convertable to XML
    upload_dict = {'row': upload_list}

    creds = (config_dict['username'], config_dict['password'])
    r = requests.post(config_dict['url'], json=upload_dict, auth=creds)
    r.raise_for_status()


def slate_post_fa_checklist(upload_list):
    """Upload Financial Aid Checklist to Slate."""

    if len(upload_list) > 0:
        # Slate's Checklist Import (Financial Aid) requires tab-separated files because it's old and crusty, apparently.
        tab = '\t'
        slate_fa_string = 'AppID' + tab + 'Code' + tab + 'Status' + tab + 'Date'
        for i in upload_list:
            line = i['AppID'] + tab + \
                str(i['Code']) + tab + i['Status'] + tab + i['Date']
            slate_fa_string = slate_fa_string + '\n' + line

        creds = (CONFIG['fa_checklist']['slate_post']['username'],
                 CONFIG['fa_checklist']['slate_post']['password'])
        r = requests.post(CONFIG['fa_checklist']['slate_post']['url'],
                          data=slate_fa_string, auth=creds)
        r.raise_for_status()


def learn_actions(actions_list):
    global CONFIG
    action_ids = []
    admissions_action_codes = CONFIG['scheduled_actions']['admissions_action_codes']

    for action_id in actions_list:
        for k, v in action_id.items():
            if k == "action_id":
                action_ids.append(v)
    learned_actions = [
        k for k in action_ids if k not in admissions_action_codes]

    # Dedupe
    learned_actions = list(set(learned_actions))

    # Sanity check against PowerCampus
    for action_id in learned_actions:
        action_def = ps_powercampus.get_action_definition(action_id)
        if action_def is None:
            learned_actions.remove(action_id)

    admissions_action_codes += learned_actions

    # Write new config
    with open(CONFIG_PATH, mode='w') as file:
        json.dump(CONFIG, file, indent='\t')


def main_sync(pid=None):
    """Main body of the program.

    Keyword arguments:
    pid -- specific application GUID to sync (default None)
    """
    global CURRENT_RECORD
    global RM_MAPPING

    verbose_print('Get applicants from Slate...')
    creds = (CONFIG['slate_query_apps']['username'],
             CONFIG['slate_query_apps']['password'])
    if pid is not None:
        r = requests.get(CONFIG['slate_query_apps']['url'],
                         auth=creds, params={'pid': pid})
    else:
        r = requests.get(CONFIG['slate_query_apps']['url'], auth=creds)
    r.raise_for_status()
    apps = json.loads(r.text)['row']
    verbose_print('\tFetched ' + str(len(apps)) + ' apps')

    # Make a dict of apps with application GUID as the key
    # {AppGUID: { JSON from Slate }
    apps = {k['aid']: k for k in apps}
    if len(apps) == 0 and pid is not None:
        # Assuming we're running in interactive (HTTP) mode if pid param exists
        raise EOFError(MSG_STRINGS['error_no_apps'])
    elif len(apps) == 0:
        # Don't raise an error for scheduled mode
        return None

    verbose_print(
        'Clean up app data from Slate (datatypes, supply nulls, etc.)')
    for k, v in apps.items():
        CURRENT_RECORD = k
        apps[k] = format_app_generic(v, CONFIG['slate_upload_active'])

    if CONFIG['autoconfigure_mappings']['enabled']:
        verbose_print('Auto-configure ProgramOfStudy and recruiterMapping.xml')
        CURRENT_RECORD = None
        mfl = CONFIG['mapping_file_location']
        vd = CONFIG['autoconfigure_mappings']['validate_degreq']
        mdy = CONFIG['autoconfigure_mappings']['minimum_degreq_year']
        dp_list = [(apps[app]['Program'], apps[app]['Degree'])
                   for app in apps if 'Degree' in apps[app]]

        if ps_powercampus.autoconfigure_mappings(dp_list, vd, mdy, mfl):
            RM_MAPPING = ps_powercampus.get_recruiter_mapping(mfl)

    verbose_print('Check each app\'s status flags/PCID in PowerCampus')
    for k, v in apps.items():
        CURRENT_RECORD = k
        status_ra, status_app, status_calc, pcid = ps_powercampus.scan_status(
            v)
        apps[k].update({'status_ra': status_ra, 'status_app': status_app,
                        'status_calc': status_calc})
        apps[k]['PEOPLE_CODE_ID'] = pcid

    verbose_print(
        'Post new or repost unprocessed applications to PowerCampus API')
    for k, v in apps.items():
        CURRENT_RECORD = k
        if (v['status_ra'] == None) or (v['status_ra'] in (1, 2) and v['status_app'] is None):
            pcid = ps_powercampus.post_api(format_app_api(
                v, CONFIG['defaults']), MSG_STRINGS)
            apps[k]['PEOPLE_CODE_ID'] = pcid

            # Rescan status
            status_ra, status_app, status_calc, pcid = ps_powercampus.scan_status(
                v)
            apps[k].update({'status_ra': status_ra, 'status_app': status_app,
                            'status_calc': status_calc})
            apps[k]['PEOPLE_CODE_ID'] = pcid

    verbose_print('Get scheduled actions from Slate')
    if CONFIG['scheduled_actions']['enabled'] == True:
        CURRENT_RECORD = None
        # Send list of app GUID's to Slate; get back checklist items
        actions_list = slate_get_actions(
            [k for (k, v) in apps.items() if v['status_calc'] == 'Active'])

        if CONFIG['scheduled_actions']['autolearn_action_codes'] == True:
            learn_actions(actions_list)

    verbose_print(
        'Update existing applications in PowerCampus and extract information')
    unmatched_schools = []
    for k, v in apps.items():
        CURRENT_RECORD = k
        if v['status_calc'] == 'Active':
            # Transform to PowerCampus format
            app_pc = format_app_sql(v, RM_MAPPING, CONFIG)
            pcid = app_pc['PEOPLE_CODE_ID']
            academic_year = app_pc['ACADEMIC_YEAR']
            academic_term = app_pc['ACADEMIC_TERM']
            academic_session = app_pc['ACADEMIC_SESSION']

            # Single-row updates
            ps_powercampus.update_demographics(app_pc)
            ps_powercampus.update_academic(app_pc)
            ps_powercampus.update_smsoptin(app_pc)
            if CONFIG['pc_update_custom_academickey'] == True:
                ps_powercampus.update_academic_key(app_pc)

            # Update PowerCampus Scheduled Actions
            if CONFIG['scheduled_actions']['enabled'] == True:
                app_actions = [k for k in actions_list if k['aid']
                               == v['aid'] and 'action_id' in k]

                for action in app_actions:
                    ps_powercampus.update_action(
                        action, pcid, academic_year, academic_term, academic_session)

                ps_powercampus.cleanup_actions(
                    CONFIG['scheduled_actions']['admissions_action_codes'], app_actions, pcid, academic_year, academic_term, academic_session)

            # Update PowerCampus Education records
            if 'Education' in app_pc:
                apps[k]['schools_not_found'] = []
                for edu in app_pc['Education']:
                    unmatched_schools.append(
                        ps_powercampus.update_education(pcid, app_pc['pid'], edu))

            # Update PowerCampus Test Score records
            if 'TestScoresNumeric' in app_pc:
                for test in app_pc['TestScoresNumeric']:
                    ps_powercampus.update_test_scores(pcid, test)

            # Update any PowerCampus Notes defined in config
            for note in CONFIG['pc_notes']:
                if note['slate_field'] in app_pc and len(app_pc[note['slate_field']]) > 0:
                    ps_powercampus.update_note(
                        app_pc, note['slate_field'], note['office'], note['note_type'])

            # Update any PowerCampus User Defined fields defined in config
            for udf in CONFIG['pc_user_defined']:
                if udf['slate_field'] in app_pc and len(app_pc[udf['slate_field']]) > 0:
                    ps_powercampus.update_udf(
                        app_pc, udf['slate_field'], udf['pc_field'])

            # Collect information
            found, registered, reg_date, readmit, withdrawn, credits, campus_email, advisor, moodle_orientation_complete = ps_powercampus.get_profile(
                app_pc)
            apps[k].update({'found': found,
                            'registered': registered,
                            'reg_date': reg_date,
                            'readmit': readmit,
                            'withdrawn': withdrawn,
                            'credits': credits,
                            'campus_email': campus_email,
                            'advisor': advisor,
                            'moodle_orientation_complete': moodle_orientation_complete})

    verbose_print('Upload passive fields back to Slate')
    slate_post_fields(apps, CONFIG['slate_upload_passive'])

    verbose_print('Upload active (changed) fields back to Slate')
    verbose_print(slate_post_fields_changed(
        apps, CONFIG['slate_upload_active']))

    if len(unmatched_schools) > 0 and unmatched_schools[0] is not None:
        verbose_print('Upload unmatched school records back to Slate')
        slate_post_generic(unmatched_schools, CONFIG['slate_upload_schools'])

    # Collect Financial Aid checklist and upload to Slate
    if CONFIG['fa_checklist']['enabled'] == True:
        verbose_print('Collect Financial Aid checklist and upload to Slate')
        slate_upload_list = []
        # slate_upload_fields = {'AppID', 'Code', 'Status', 'Date'}

        for k, v in apps.items():
            CURRENT_RECORD = k
            if v['status_calc'] == 'Active':
                # Transform to PowerCampus format
                app_pc = format_app_sql(v, RM_MAPPING, CONFIG)

                fa_checklists = ps_powercampus.pf_get_fachecklist(
                    app_pc['PEOPLE_CODE_ID'], v['GovernmentId'], v['AppID'], app_pc['ACADEMIC_YEAR'], app_pc['ACADEMIC_TERM'], app_pc['ACADEMIC_SESSION'])

                slate_upload_list = slate_upload_list + fa_checklists

        slate_post_fa_checklist(slate_upload_list)

    return MSG_STRINGS['sync_done']