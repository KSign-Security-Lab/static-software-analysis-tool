#include <syslog.h>

void audit_event_bad(const char *detail) {
    syslog(LOG_INFO, detail);
}
