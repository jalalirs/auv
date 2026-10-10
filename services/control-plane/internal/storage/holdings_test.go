package storage

import (
	"reflect"
	"testing"
)

func TestASmallUploadIsOnePartAndAVideoIsMany(t *testing.T) {
	if plan := planParts(10<<20, DefaultPartBytes); plan.Count != 1 || plan.PartBytes != 10<<20 {
		t.Fatalf("a 10 MB survey: %+v", plan)
	}
	video := int64(4) << 30 // ten minutes of GoPro 4K
	plan := planParts(video, DefaultPartBytes)
	if plan.Count != 128 || plan.PartBytes != DefaultPartBytes {
		t.Fatalf("a 4 GB video: %+v", plan)
	}
	odd := video + 12345
	plan = planParts(odd, DefaultPartBytes)
	if plan.Count != 129 || partSize(plan, odd, 129) != 12345 || partSize(plan, odd, 128) != DefaultPartBytes {
		t.Fatalf("the last part carries what is left: %+v, last %d", plan, partSize(plan, odd, 129))
	}
}

func TestAResumedUploadSendsOnlyWhatDidNotArrive(t *testing.T) {
	size := 3*DefaultPartBytes + 7
	plan := planParts(size, DefaultPartBytes)
	held := []Part{
		{Number: 1, SizeBytes: DefaultPartBytes},
		{Number: 3, SizeBytes: DefaultPartBytes / 2}, // cut off halfway
		{Number: 4, SizeBytes: 7},
	}
	if got := missingParts(held, plan, size); !reflect.DeepEqual(got, []int{2, 3}) {
		t.Fatalf("missing %v, want [2 3]", got)
	}
	all := append(held[:1:1], Part{Number: 2, SizeBytes: DefaultPartBytes},
		Part{Number: 3, SizeBytes: DefaultPartBytes}, Part{Number: 4, SizeBytes: 7})
	if got := missingParts(all, plan, size); len(got) != 0 {
		t.Fatalf("all arrived, missing %v", got)
	}
}

func TestAnUploadThatWouldPassTheLimitIsRefused(t *testing.T) {
	limit := int64(100)
	if !fits(60, 0, limit, 40) {
		t.Fatal("exactly to the limit fits")
	}
	if fits(60, 30, limit, 20) {
		t.Fatal("uploads already on their way count")
	}
	err := &OverLimit{UsedBytes: 90, LimitBytes: 100, AskedBytes: 20}
	if err.Error() == "" {
		t.Fatal("the refusal says why")
	}
}
