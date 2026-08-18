#include <stdlib.h>
#include <string.h>

void store_frame_fixed(const unsigned char *src, size_t len) {
    /* allocate for what will actually be written */
    unsigned char *buf = malloc(len);
    if (buf == NULL) return;
    memcpy(buf, src, len);
    submit(buf, len);
}
