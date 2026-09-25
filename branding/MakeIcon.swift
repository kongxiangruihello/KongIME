import Cocoa
import CoreGraphics
let out=CommandLine.arguments[1]
func drawK(_ c:CGContext,_ color:CGColor){
 c.saveGState()
 c.translateBy(x:1.134,y:1.548)
 c.scaleBy(x:0.828,y:0.828)
 c.setFillColor(color)
 let p=CGMutablePath()
 p.move(to:CGPoint(x:3,y:2));p.addLine(to:CGPoint(x:6,y:2));p.addLine(to:CGPoint(x:6,y:7.5));p.addLine(to:CGPoint(x:11.8,y:2));p.addLine(to:CGPoint(x:16,y:2));p.addLine(to:CGPoint(x:8.5,y:9));p.addLine(to:CGPoint(x:15.5,y:16));p.addLine(to:CGPoint(x:11.5,y:16));p.addLine(to:CGPoint(x:6,y:10.4));p.addLine(to:CGPoint(x:6,y:16));p.addLine(to:CGPoint(x:3,y:16));p.closeSubpath();c.addPath(p);c.setStrokeColor(color);c.setLineWidth(0.22);c.setLineJoin(.round);c.drawPath(using:.fillStroke);c.restoreGState()
}
var rect=CGRect(x:0,y:0,width:18,height:18)
let pdf=CGContext(URL(fileURLWithPath:out+"/rime.pdf") as CFURL,mediaBox:&rect,nil)!
pdf.beginPDFPage(nil);drawK(pdf,CGColor(gray:0,alpha:1));pdf.endPDFPage();pdf.closePDF()
let preview=NSImage(size:NSSize(width:480,height:160));preview.lockFocus()
let c=NSGraphicsContext.current!.cgContext
for (x,dark) in [(0.0,false),(240.0,true)]{
 c.setFillColor(CGColor(gray:dark ? 0.12:0.96,alpha:1));c.fill(CGRect(x:x,y:0,width:240,height:160));c.saveGState();c.translateBy(x:x+88,y:40);c.scaleBy(x:4,y:4);drawK(c,CGColor(gray:dark ? 1:0,alpha:1));c.restoreGState()
}
preview.unlockFocus()
let bitmap=NSBitmapImageRep(data:preview.tiffRepresentation!)!
try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:out+"/K-preview.png"))
