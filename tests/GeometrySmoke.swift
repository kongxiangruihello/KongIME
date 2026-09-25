import Foundation
import CoreGraphics
@main struct GeometrySmoke {
 static func main() {
  let screens = [CGRect(x:0,y:0,width:1440,height:900),CGRect(x:-1920,y:100,width:1920,height:1080),CGRect(x:0,y:900,width:1440,height:900)]
  precondition(CandidateGeometry.screenIndex(anchor:CGRect(x:-1200,y:500,width:1,height:18),frames:screens)==1)
  precondition(CandidateGeometry.screenIndex(anchor:CGRect(x:700,y:1000,width:1,height:18),frames:screens)==2)
  precondition(CandidateGeometry.screenIndex(anchor:CGRect(x:-3000,y:500,width:1,height:18),frames:screens)==1)
  var count=0
  for area in screens {
   for x in [area.minX-200,area.midX,area.maxX+200] {
    for y in [area.minY-200,area.midY,area.maxY+200] {
     for size in [CGSize(width:300,height:200),CGSize(width:3000,height:3000)] {
      let r=CandidateGeometry.contained(CGRect(origin:CGPoint(x:x,y:y),size:size),in:area)
      precondition(r.minX>=area.minX && r.maxX<=area.maxX && r.minY>=area.minY && r.maxY<=area.maxY);count += 1
     }
    }
   }
  }
  print("Simulated multi-monitor geometry checks: \(count), plus screen-selection cases")
  var avoidanceChecks = 0
  for area in screens {
   for y in [area.minY,area.midY,area.maxY-18] {
    for height: CGFloat in [60,84,800,3000] {
     for gap: CGFloat in [8,12,18,24] {
      let anchor=CGRect(x:area.midX,y:y,width:1,height:18)
      let frame=CandidateGeometry.avoidingLine(CGRect(x:anchor.minX,y:0,width:3000,height:height),anchor:anchor,in:area,gap:gap)
      precondition(frame.minX>=area.minX && frame.maxX<=area.maxX && frame.minY>=area.minY && frame.maxY<=area.maxY)
      precondition(frame.maxY<=anchor.minY-gap || frame.minY>=anchor.maxY+gap,"Candidate covers composition")
      precondition(frame.height>0);avoidanceChecks += 1
     }
    }
   }
  }
  let anchor=CGRect(x:300,y:500,width:1,height:24)
  let frame=CandidateGeometry.avoidingLine(CGRect(x:300,y:420,width:500,height:104),anchor:anchor,in:screens[0],gap:8)
  precondition(frame.maxY==492,"Expansion footer must move the whole window down")
  print("Input-line avoidance checks: \(avoidanceChecks), plus expansion-footer regression")
 }
}
