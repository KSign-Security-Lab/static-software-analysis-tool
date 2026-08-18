#include <string.h>

void take_packet_fixed(const unsigned char *src, unsigned int len) {
    /* the copy is clamped to what body can hold */
    unsigned char body[128];
    if (len > sizeof(body)) len = sizeof(body);
    memcpy(body, src, len);
    parse(body, len);
}
