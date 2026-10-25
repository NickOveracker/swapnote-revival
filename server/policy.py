"""SpotPass policy list served to consoles patched with BOSS patch 02.

BOSS fetches GET /p01/policylist/<majorVersion>/<country>[?ap=...] and stops every task
that the list does not allow. Nintendo's own list stops Swapnote's tasks, so we serve one
with DefaultStop=false and Swapnote's friend-note tasks at HIGH priority.
Format as served by Pretendo's SpotPass server (plain XML, no declaration, unsigned).
"""
import re
import time

SWAPNOTE = '0004000000051700'
# Upload slots JFR_U01..07 (sending) and JFR_DFR (receiving friend notes).
SWAPNOTE_TASKS = [f'JFR_U{i:02d}' for i in range(1, 8)] + ['JFR_DFR']

# Bump when the list content changes, so consoles replace their cached copy.
LIST_ID = 20261025


def policy_list(path):
    """Return (status, body) for a policy list request path."""
    m = re.fullmatch(r'/p01/policylist/(\d+)/([A-Za-z0-9]+)', path.split('?', 1)[0])
    if not m or m.group(1) != '3':
        return 404, b''
    entries = ''.join(
        f'  <Priority>\n'
        f'    <TitleId>{SWAPNOTE}</TitleId>\n'
        f'    <TaskId>{task}</TaskId>\n'
        f'    <Level>HIGH</Level>\n'
        f'    <Persistent>true</Persistent>\n'
        f'    <Revive>true</Revive>\n'
        f'  </Priority>\n' for task in SWAPNOTE_TASKS)
    xml = (f'<PolicyList>\n'
           f'  <MajorVersion>3</MajorVersion>\n'
           f'  <MinorVersion>0</MinorVersion>\n'
           f'  <ListId>{LIST_ID}</ListId>\n'
           f'  <DefaultStop>false</DefaultStop>\n'
           f'  <ForceVersionUp>false</ForceVersionUp>\n'
           f'  <UpdateTime>{time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime())}</UpdateTime>\n'
           f'{entries}'
           f'</PolicyList>\n')
    return 200, xml.encode()
