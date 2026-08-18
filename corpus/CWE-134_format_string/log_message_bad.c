#include <stdio.h>

void log_message_bad(const char *msg) {
    /* msg is the format, so %n and %s in it are directives */
    printf(msg);
}
