#include <string.h>

void take_packet_bad(const unsigned char *src, unsigned int len) {
    /* len is read off the wire and never compared with the buffer */
    unsigned char body[128];
    memcpy(body, src, len);
    parse(body, len);
}
