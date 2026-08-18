#include <string.h>

void copy_label_bad(const char *in) {
    /* strcpy writes until the source terminator, the buffer holds 16 */
    char label[16];
    strcpy(label, in);
    use(label);
}
