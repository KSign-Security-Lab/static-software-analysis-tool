#include <stddef.h>

int check_bound_bad(int offset, int count) {
    /* offset + count can wrap past the comparison and come back small */
    if (offset + count > 4096) return -1;
    return offset + count;
}
