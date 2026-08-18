#include <stdio.h>

void extract_entry_bad(const char *entry, const char *data) {
    /* archive entry names are attacker data and routinely contain ../ */
    char out[512];
    snprintf(out, sizeof(out), "./unpack/%s", entry);
    FILE *f = fopen(out, "wb");
    if (f != NULL) { fputs(data, f); fclose(f); }
}
