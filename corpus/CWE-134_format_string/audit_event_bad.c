#include <syslog.h>

void audit_event_bad(const char *detail) {
    /* syslog takes a format too, and this one comes from input */
    syslog(LOG_INFO, detail);
}
