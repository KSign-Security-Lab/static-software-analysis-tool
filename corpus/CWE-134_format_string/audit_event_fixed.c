#include <syslog.h>

void audit_event_fixed(const char *detail) {
    syslog(LOG_INFO, "%s", detail);
}
