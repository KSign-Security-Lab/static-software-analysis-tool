#include <stdio.h>

void log_message_fixed(const char *msg) {
    /* the format is a literal and msg is only ever an argument */
    printf("%s", msg);
}
