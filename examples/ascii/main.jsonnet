local ascii = import 'xtd/ascii.libsonnet';
assert ascii.isLower('a');
assert !ascii.isLower('A');
{ purified: ascii.isStringNumeric('12345') }
