#include <stdlib.h>
#include <string.h>

void store_frame_bad(const unsigned char *src, size_t len) {
    /* the allocation is a fixed size and the copy is not */
    unsigned char *buf = malloc(256);
    memcpy(buf, src, len);
    submit(buf, len);
}
