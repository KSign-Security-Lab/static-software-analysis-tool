#include <string.h>

void take_packet_fixed(const unsigned char *src, unsigned int avail, unsigned int len) {
    /* clamped to what body holds *and* to what src actually has */
    unsigned char body[128];
    if (len > avail) len = avail;
    if (len > sizeof(body)) len = sizeof(body);
    memcpy(body, src, len);
    parse(body, len);
}
